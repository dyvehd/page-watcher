import asyncio
import logging
from datetime import datetime, timezone
import os
from typing import Dict, Set, Tuple

from src.config import AppConfig, PageConfig, GroupConfig
from src.database import Database
from src.browser import BrowserManager
from src.parser import clean_html, get_content_hash, generate_diff
from src.notifier import DiscordNotifier

logger = logging.getLogger(__name__)

class WatcherScheduler:
    def __init__(self, config: AppConfig, db_path: str = "watcher.db"):
        self.config = config
        self.db = Database(db_path)
        self.browser_mgr = BrowserManager(use_camoufox=True)
        self.notifier = DiscordNotifier(config.discord_webhook_url)
        # Keep track of active tasks and error states in memory to avoid spamming alerts
        self.running_tasks: Set[Tuple[str, str]] = set()
        self.failed_pages: Dict[Tuple[str, str], str] = {} # (group_key, page_key) -> last_error_message
        self.failure_counts: Dict[Tuple[str, str], int] = {} # (group_key, page_key) -> consecutive_failure_count

    def _get_page_interval(self, page_config: PageConfig) -> int:
        """Determines the check interval in seconds for a page."""
        if page_config.check_interval_seconds is not None:
            return page_config.check_interval_seconds
        return self.config.check_interval_seconds

    def _get_screenshot_policy(self, group_config: GroupConfig, page_config: PageConfig) -> str:
        """Determines the screenshot policy ('always', 'on_change', 'never') for a page."""
        val = None
        if page_config.save_screenshot is not None:
            val = page_config.save_screenshot
        elif group_config.save_screenshot is not None:
            val = group_config.save_screenshot
        else:
            val = self.config.save_screenshots

        # Normalize to string
        if val is True or val == "always":
            return "always"
        if val is False or val == "never":
            return "never"
        if val == "on_change":
            return "on_change"
        return "on_change" # Default fallback

    async def check_page(self, group_key: str, group_config: GroupConfig, page_config: PageConfig):
        """Executes a full watch check for a single page."""
        task_id = (group_key, page_config.key)
        if task_id in self.running_tasks:
            logger.debug(f"Check already running for page {group_key}/{page_config.key}. Skipping.")
            return

        self.running_tasks.add(task_id)
        logger.info(f"Starting check for: {group_config.name} -> {page_config.name}")

        try:
            # 1. Fetch raw HTML and screenshot
            policy = self._get_screenshot_policy(group_config, page_config)
            save_screenshot = (policy != "never")
            html_content, screenshot_path = await self.browser_mgr.fetch_page(
                group_key=group_key,
                page_config=page_config,
                login_config=group_config.login,
                db=self.db,
                save_screenshot=save_screenshot,
                api_handler=group_config.api_handler
            )

            # 2. Parse and clean HTML content
            cleaned_text = clean_html(
                html_content=html_content,
                selector=page_config.selector,
                exclude_selectors=page_config.exclude
            )

            # 3. Calculate content hash
            new_hash = get_content_hash(cleaned_text)

            # 4. Fetch the last saved state from database
            last_state = self.db.get_last_page_state(group_key, page_config.key)
            
            if last_state is None:
                # First-time run: save current state as baseline and notify user comparing against empty
                logger.info(f"First-time run for page {page_config.name}. Saving baseline and sending initial notification.")
                state_id = self.db.save_page_state(
                    group_key=group_key,
                    page_key=page_config.key,
                    content_hash=new_hash,
                    cleaned_content=cleaned_text,
                    screenshot_path=screenshot_path
                )
                self.db.update_page_check(group_key, page_config.key, content_hash=new_hash, did_change=True)
                
                # Generate diff from empty content to show initial baseline
                diff_summary = generate_diff("", cleaned_text)
                
                # Log baseline in change history
                self.db.save_change_history(
                    group_key=group_key,
                    page_key=page_config.key,
                    old_state_id=None,
                    new_state_id=state_id,
                    diff_summary=diff_summary
                )
                
                # Send Discord notification
                await self.notifier.send_change_notification(
                    group_name=group_config.name,
                    page_name=f"{page_config.name} (Initial Setup)",
                    url=page_config.url,
                    diff_summary=diff_summary,
                    screenshot_path=screenshot_path
                )
            else:
                old_hash = last_state["content_hash"]
                old_text = last_state["cleaned_content"]
                
                if old_hash == new_hash:
                    logger.info(f"No changes detected for: {page_config.name}")
                    self.db.update_page_check(group_key, page_config.key, content_hash=new_hash, did_change=False)
                    # Clean up the unused screenshot to save space if policy is 'on_change'
                    if policy == "on_change" and screenshot_path and os.path.exists(screenshot_path):
                        try:
                            os.remove(screenshot_path)
                        except OSError:
                            pass
                else:
                    logger.info(f"🚨 CHANGE DETECTED for page: {page_config.name}")
                    
                    # Generate unified line diff
                    diff_summary = generate_diff(old_text, cleaned_text)
                    
                    # Save new state
                    new_state_id = self.db.save_page_state(
                        group_key=group_key,
                        page_key=page_config.key,
                        content_hash=new_hash,
                        cleaned_content=cleaned_text,
                        screenshot_path=screenshot_path
                    )
                    
                    # Log diff in history
                    self.db.save_change_history(
                        group_key=group_key,
                        page_key=page_config.key,
                        old_state_id=last_state["id"],
                        new_state_id=new_state_id,
                        diff_summary=diff_summary
                    )
                    
                    # Update page meta
                    self.db.update_page_check(group_key, page_config.key, content_hash=new_hash, did_change=True)
                    
                    # Housekeeping: Keep last 10 states
                    self.db.clean_old_states(group_key, page_config.key, keep_limit=10)
                    
                    # Send Discord notification
                    await self.notifier.send_change_notification(
                        group_name=group_config.name,
                        page_name=page_config.name,
                        url=page_config.url,
                        diff_summary=diff_summary,
                        screenshot_path=screenshot_path
                    )
            
            # Clear from error state memory if it succeeded
            self.failure_counts[task_id] = 0
            if task_id in self.failed_pages:
                del self.failed_pages[task_id]
                logger.info(f"Page {page_config.name} recovered from previous failures.")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error checking page {page_config.name}: {error_msg}", exc_info=True)
            
            # Increment failure count
            self.failure_counts[task_id] = self.failure_counts.get(task_id, 0) + 1
            consecutive_failures = self.failure_counts[task_id]
            threshold = self.config.error_retry_threshold
            
            logger.info(f"Page {page_config.name} failed check. Consecutive failures: {consecutive_failures}/{threshold}")
            
            if consecutive_failures >= threshold:
                # Only notify on transition to failed state (consecutive_failures == threshold) or if the error message changed
                if self.failed_pages.get(task_id) != error_msg:
                    self.failed_pages[task_id] = error_msg
                    await self.notifier.send_error_notification(
                        group_name=group_config.name,
                        page_name=f"{page_config.name} ({consecutive_failures} consecutive failures)",
                        error_msg=error_msg
                    )
            
            # Update check timestamp even if it failed so we don't spam the server continuously in a tight loop
            self.db.update_page_check(group_key, page_config.key, content_hash=None, did_change=False)

        finally:
            self.running_tasks.remove(task_id)

    async def run_once(self):
        """Iterates over all configured pages and runs checks if they are due."""
        now = datetime.now(timezone.utc)
        tasks = []

        for group_key, group_config in self.config.groups.items():
            for page_config in group_config.pages:
                page_meta = self.db.get_page_meta(group_key, page_config.key)
                
                should_check = False
                if not page_meta or not page_meta["last_checked_at"]:
                    should_check = True
                else:
                    last_checked = datetime.fromisoformat(page_meta["last_checked_at"]).replace(tzinfo=timezone.utc)
                    interval = self._get_page_interval(page_config)
                    time_diff = (now - last_checked).total_seconds()
                    
                    if time_diff >= interval:
                        should_check = True
                
                if should_check:
                    tasks.append(
                        self.check_page(group_key, group_config, page_config)
                    )

        if tasks:
            logger.info(f"Scheduling {len(tasks)} page checks...")
            await asyncio.gather(*tasks, return_exceptions=True)

    async def start(self, poll_interval_seconds: int = 15):
        """Starts the scheduler daemon loop."""
        logger.info(f"Page Watcher Scheduler daemon started. Polling every {poll_interval_seconds}s.")
        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Error in scheduler run loop: {e}", exc_info=True)
            await asyncio.sleep(poll_interval_seconds)
