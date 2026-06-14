import os
import logging
import asyncio
import urllib.parse
import importlib.util
from typing import List, Dict, Any, Tuple, Optional
from src.config import LoginRecipeStep, LoginConfig, PageConfig
from src.database import Database
from src.handlers import get_api_handler

logger = logging.getLogger(__name__)

# Try to import Camoufox, fallback to standard playwright if not installed/available
try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_AVAILABLE = True
except ImportError:
    CAMOUFOX_AVAILABLE = False

from playwright.async_api import async_playwright

class BrowserManager:
    def __init__(self, use_camoufox: bool = True):
        # Allow overriding Camoufox even if available (e.g. via config/flag)
        self.use_camoufox = use_camoufox and CAMOUFOX_AVAILABLE
        self.group_locks: Dict[str, asyncio.Lock] = {}
        if self.use_camoufox:
            logger.info("Using Camoufox for browser automation.")
        else:
            logger.info("Using standard Playwright Firefox for browser automation.")

    def get_group_lock(self, group_key: str) -> asyncio.Lock:
        if group_key not in self.group_locks:
            self.group_locks[group_key] = asyncio.Lock()
        return self.group_locks[group_key]

    async def _get_browser_context(self, playwright_inst, storage_state: Optional[Dict[str, Any]] = None):
        """Launches the browser and returns a cleanup callback and context."""
        headless = True
        
        if self.use_camoufox:
            # AsyncCamoufox is a context manager. __aenter__ launches browser and returns Browser object
            browser_cm = AsyncCamoufox(headless=headless)
            browser = await browser_cm.__aenter__()
            context = await browser.new_context(storage_state=storage_state)
            
            async def close_browser():
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser_cm.__aexit__(None, None, None)
                except Exception:
                    pass
                    
            return close_browser, context
        else:
            # Fallback to standard Firefox
            browser = await playwright_inst.firefox.launch(headless=headless)
            context = await browser.new_context(storage_state=storage_state)
            
            async def close_browser():
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
                    
            return close_browser, context

    async def execute_recipe(self, page, recipe: List[LoginRecipeStep]):
        """Executes a list of login actions on the page."""
        for step in recipe:
            action = step.action
            logger.info(f"Executing recipe step: {action} (selector={step.selector}, url={step.url})")
            
            if action == "navigate":
                if not step.url:
                    raise ValueError("navigate step requires url")
                await page.goto(step.url, wait_until="networkidle")
                
            elif action == "fill":
                if not step.selector or step.value is None:
                    raise ValueError("fill step requires selector and value")
                await page.wait_for_selector(step.selector, state="visible", timeout=10000)
                await page.fill(step.selector, step.value)
                
            elif action == "click":
                if not step.selector:
                    raise ValueError("click step requires selector")
                await page.wait_for_selector(step.selector, state="visible", timeout=10000)
                await page.click(step.selector)
                
            elif action == "wait_for":
                if not step.selector:
                    raise ValueError("wait_for step requires selector")
                timeout = step.timeout if step.timeout else 10000
                await page.wait_for_selector(step.selector, state="visible", timeout=timeout)
                
            elif action == "wait_ms":
                if not step.value:
                    raise ValueError("wait_ms step requires a duration value")
                try:
                    duration = int(step.value)
                except ValueError:
                    raise ValueError(f"wait_ms step value must be an integer: {step.value}")
                await page.wait_for_timeout(duration)
                
            elif action == "wait_for_url":
                if not step.url and not step.value:
                    raise ValueError("wait_for_url step requires url or value")
                target_url = step.url if step.url else step.value
                timeout = step.timeout if step.timeout else 15000
                logger.info(f"Waiting for URL to match: {target_url} (timeout={timeout}ms)")
                await page.wait_for_url(target_url, timeout=timeout)

    async def execute_custom_script(self, script_path: str, page, credentials: Dict[str, Any]):
        """Dynamically imports and executes a custom Python login script."""
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Custom login script not found at: {script_path}")
            
        spec = importlib.util.spec_from_file_location("custom_login_module", script_path)
        if not spec or not spec.loader:
            raise ImportError(f"Failed to load module spec for: {script_path}")
            
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if not hasattr(module, "run_login"):
            raise AttributeError(f"Custom script {script_path} must define an async function 'run_login(page, credentials)'")
            
        logger.info(f"Running custom login script: {script_path}")
        await module.run_login(page, credentials)

    async def check_is_logged_in(self, page, success_selector: Optional[str]) -> bool:
        """Determines if the page is currently logged in based on the presence of a success selector."""
        if not success_selector:
            # If no success selector is specified, assume logged in
            return True
        try:
            # Check if success selector exists and is visible (short timeout)
            await page.wait_for_selector(success_selector, state="visible", timeout=5000)
            return True
        except Exception:
            return False

    async def fetch_page(
        self,
        group_key: str,
        page_config: PageConfig,
        login_config: LoginConfig,
        db: Database,
        save_screenshot: bool = True,
        screenshots_dir: str = "screenshots",
        api_handler: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Loads the page, running the login recipe if necessary, saving/updating cookies,
        taking a screenshot, and returning the HTML content.
        
        Returns:
            Tuple[str, Optional[str]]: (HTML content of the page, path to the screenshot image file)
        """
        lock = self.get_group_lock(group_key)
        async with lock:
            return await self._fetch_page_unlocked(group_key, page_config, login_config, db, save_screenshot, screenshots_dir, api_handler)

    async def _fetch_page_unlocked(
        self,
        group_key: str,
        page_config: PageConfig,
        login_config: LoginConfig,
        db: Database,
        save_screenshot: bool = True,
        screenshots_dir: str = "screenshots",
        api_handler: Optional[str] = None
    ) -> Tuple[str, Optional[str]]:
        os.makedirs(screenshots_dir, exist_ok=True)
        
        # Load existing session cookies/localStorage from SQLite
        cookies, local_storage = db.get_group_session(group_key)
        storage_state = {}
        if cookies:
            storage_state["cookies"] = cookies
        if local_storage:
            storage_state["origins"] = local_storage
            
        if not storage_state:
            storage_state = None

        async with async_playwright() as p:
            close_browser, context = await self._get_browser_context(p, storage_state)
            try:
                page = await context.new_page()
                
                # Check login if login recipe or script is specified
                needs_login = False
                success_selector = None
                
                if login_config.type == "recipe" and login_config.recipe:
                    # Find success selector if specified (usually the wait_for selector in recipe)
                    for step in reversed(login_config.recipe):
                        if step.action == "wait_for" and step.selector:
                            success_selector = step.selector
                            break
                
                if login_config.type in ("recipe", "script"):
                    if storage_state:
                        # Try navigating directly to the page to see if we are already logged in
                        is_api = "/api/" in page_config.url
                        verify_url = page_config.url
                        if is_api:
                            # For API endpoints, verify session using the base dashboard URL
                            parsed = urllib.parse.urlparse(page_config.url)
                            verify_url = urllib.parse.urlunparse(parsed[:2] + ('/app/', '', '', ''))
                            
                        logger.info(f"Attempting direct navigation to verify active session: {verify_url}")
                        await page.goto(verify_url, wait_until="networkidle")
                        
                        # Detect redirects to SSO/login domains
                        current_url = page.url
                        redirected_to_sso = False
                        target_domain = urllib.parse.urlparse(verify_url).netloc
                        current_domain = urllib.parse.urlparse(current_url).netloc
                        
                        if target_domain != current_domain or "login" in current_url.lower() or "sso" in current_url.lower():
                            redirected_to_sso = True
                        
                        is_logged_in = True
                        if redirected_to_sso:
                            is_logged_in = False
                        elif login_config.type == "recipe" and success_selector:
                            is_logged_in = await self.check_is_logged_in(page, success_selector)
                            
                        if not is_logged_in:
                            logger.info("Session expired or redirected to SSO. Running login process.")
                            needs_login = True
                    else:
                        logger.info("No saved session cookies found. Login required.")
                        needs_login = True
                
                if needs_login:
                    if login_config.type == "recipe":
                        # Execute login steps
                        await self.execute_recipe(page, login_config.recipe)
                    elif login_config.type == "script":
                        if not login_config.script_path:
                            raise ValueError("script login type requires script_path to be specified")
                        await self.execute_custom_script(login_config.script_path, page, login_config.credentials)
                    
                    # Capture new session state and persist to database
                    new_state = await context.storage_state()
                    db.save_group_session(
                        group_key,
                        new_state.get("cookies", []),
                        new_state.get("origins", [])
                    )
                    logger.info(f"Saved fresh session cookies/localStorage for group: {group_key}")
                
                is_api = "/api/" in page_config.url
                
                if is_api:
                    if api_handler:
                        logger.info(f"Using custom API handler: {api_handler}")
                        if not os.path.exists(api_handler):
                            raise FileNotFoundError(f"Custom API handler script not found at: {api_handler}")
                            
                        spec = importlib.util.spec_from_file_location("custom_api_handler_module", api_handler)
                        if not spec or not spec.loader:
                            raise ImportError(f"Failed to load module spec for: {api_handler}")
                            
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        if not hasattr(module, "fetch_api"):
                            raise AttributeError(f"Custom API handler {api_handler} must define an async function 'fetch_api(page, api_url)'")
                            
                        api_data = await module.fetch_api(page, page_config.url)
                    else:
                        handler = get_api_handler(page_config.url)
                        api_data = await handler.fetch_api(page, page_config.url)
                    
                    # Display JSON content inside pre tag for screenshots
                    await page.evaluate("""(data) => {
                        document.body.innerHTML = `<pre style="font-family: monospace; white-space: pre-wrap; word-wrap: break-word; padding: 20px; font-size: 14px; color: #333; background: #f8f9fa;">${data}</pre>`;
                    }""", api_data)
                    
                    html_content = api_data
                else:
                    # Navigate to the target page if we haven't already or if we had to log in
                    if needs_login or not page.url.startswith(page_config.url):
                        logger.info(f"Navigating to watch page: {page_config.url}")
                        await page.goto(page_config.url, wait_until="networkidle")
                    
                    # If a page-level selector is configured, wait for it to render
                    if page_config.selector:
                        try:
                            await page.wait_for_selector(page_config.selector, state="attached", timeout=15000)
                        except Exception:
                            logger.warning(f"Timeout waiting for page selector: {page_config.selector}")
                    
                    # Get page source
                    html_content = await page.content()
                
                screenshot_path = None
                if save_screenshot:
                    # Take screenshot
                    screenshot_filename = f"{group_key}_{page_config.key}_{int(asyncio.get_event_loop().time())}.png"
                    screenshot_path = os.path.join(screenshots_dir, screenshot_filename)
                    
                    # Capture full page screenshot
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"Saved page screenshot to: {screenshot_path}")
                
                # Get page source
                html_content = await page.content()
                
                return html_content, screenshot_path
                
            finally:
                await close_browser()
