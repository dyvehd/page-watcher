import logging
import urllib.parse

logger = logging.getLogger(__name__)

async def fetch_api(page, api_url: str) -> str:
    """
    Specialized handler for HCMUT MyBK API. Navigates to `/app/` context,
    checks DOM inputs (like `#hid_Token`) in addition to storage, and executes the fetch.
    """
    parsed_url = urllib.parse.urlparse(api_url)
    # MyBK SPA lives under /app/
    target_origin = urllib.parse.urlunparse(parsed_url[:2] + ('/app/', '', '', ''))
    current_origin = urllib.parse.urlunparse(urllib.parse.urlparse(page.url)[:2] + ('', '', '', ''))
    
    if target_origin != current_origin:
        logger.info(f"MyBK handler: Navigating to SPA context {target_origin}...")
        await page.goto(target_origin, wait_until="networkidle")
        
    logger.info(f"MyBK handler: Executing API fetch in page context for: {api_url}")
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
        
        // 4. Search in DOM input elements (e.g. hidden inputs like #hid_Token)
        if (!authHeader) {
            const hidTokenEl = document.getElementById("hid_Token");
            if (hidTokenEl && hidTokenEl.value) {
                let token = findJwt(hidTokenEl.value);
                if (token) { authHeader = token; }
            }
        }

        // 5. General DOM search for hidden inputs/elements with JWT
        if (!authHeader) {
            const inputs = document.querySelectorAll("input");
            for (let input of inputs) {
                if (input.value) {
                    let token = findJwt(input.value);
                    if (token) { authHeader = token; break; }
                }
            }
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
