import logging
import urllib.parse
from typing import Dict

logger = logging.getLogger(__name__)

class BaseApiHandler:
    """Base class for handling API requests and injecting authorization headers."""
    
    async def fetch_api(self, page, api_url: str) -> str:
        """Navigates to the appropriate page context, extracts auth tokens, and fetches the API."""
        raise NotImplementedError("API handlers must implement fetch_api")

class DefaultApiHandler(BaseApiHandler):
    """
    Default handler for APIs. Navigates to the base origin, checks standard storage 
    (localStorage, sessionStorage, cookies) for a JWT token, and executes the fetch.
    """
    
    async def fetch_api(self, page, api_url: str) -> str:
        parsed_url = urllib.parse.urlparse(api_url)
        # Default to navigating to the base origin (e.g. https://domain.com/)
        target_origin = urllib.parse.urlunparse(parsed_url[:2] + ('/', '', '', ''))
        current_origin = urllib.parse.urlunparse(urllib.parse.urlparse(page.url)[:2] + ('', '', '', ''))
        
        if target_origin != current_origin:
            logger.info(f"DefaultApiHandler: Navigating to origin context {target_origin}...")
            await page.goto(target_origin, wait_until="networkidle")
            
        logger.info(f"DefaultApiHandler: Executing API fetch in page context for: {api_url}")
        return await page.evaluate(r"""async (url) => {
            const findJwt = (obj) => {
                if (!obj) return null;
                if (typeof obj === 'string') {
                    const match = obj.match(/eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/);
                    if (match) return match[0];
                    if (obj.startsWith("eyJ") && obj.split('.').length >= 3) return obj;
                    return null;
                }
                if (typeof obj === 'object') {
                    for (let key in obj) {
                        try {
                            const res = findJwt(obj[key]);
                            if (res) return res;
                        } catch (e) {}
                    }
                }
                return null;
            };

            let authHeader = "";
            
            // 1. Search in localStorage
            for (let i = 0; i < localStorage.length; i++) {
                let k = localStorage.key(i);
                let v = localStorage.getItem(k);
                if (!v) continue;
                let token = findJwt(v);
                if (token) { authHeader = token; break; }
                try {
                    let parsed = JSON.parse(v);
                    let tokenInJson = findJwt(parsed);
                    if (tokenInJson) { authHeader = tokenInJson; break; }
                } catch (e) {}
            }
            
            // 2. Search in sessionStorage
            if (!authHeader) {
                for (let i = 0; i < sessionStorage.length; i++) {
                    let k = sessionStorage.key(i);
                    let v = sessionStorage.getItem(k);
                    if (!v) continue;
                    let token = findJwt(v);
                    if (token) { authHeader = token; break; }
                    try {
                        let parsed = JSON.parse(v);
                        let tokenInJson = findJwt(parsed);
                        if (tokenInJson) { authHeader = tokenInJson; break; }
                    } catch (e) {}
                }
            }

            // 3. Search in cookies
            if (!authHeader) {
                let token = findJwt(document.cookie);
                if (token) { authHeader = token; }
            }
            
            const headers = { 'accept': 'application/json' };
            if (authHeader) {
                headers['authorization'] = authHeader.startsWith('Bearer ') ? authHeader : `Bearer ${authHeader}`;
            }
            
            const r = await fetch(url, { headers });
            if (!r.ok) {
                throw new Error(`API fetch failed with status: ${r.status}`);
            }
            return await r.text();
        }""", api_url)

# Registry mapping hostnames to their specialized handlers
_HANDLERS: Dict[str, BaseApiHandler] = {}

def get_api_handler(api_url: str) -> BaseApiHandler:
    """Returns the appropriate API handler based on the URL hostname."""
    parsed = urllib.parse.urlparse(api_url)
    hostname = parsed.hostname or ""
    # Strip 'www.' if present
    if hostname.startswith("www."):
        hostname = hostname[4:]
        
    handler = _HANDLERS.get(hostname)
    if handler:
        logger.debug(f"get_api_handler: Selected custom handler for {hostname}")
        return handler
        
    logger.debug(f"get_api_handler: Selected DefaultApiHandler for {hostname}")
    return DefaultApiHandler()
