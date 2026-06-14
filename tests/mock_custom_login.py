# Mock custom login script for testing dynamic script execution
import logging

logger = logging.getLogger(__name__)

async def run_login(page, credentials):
    logger.info("Executing mock custom python login script...")
    
    # 1. Navigate to login using credentials['login_url']
    login_url = credentials.get("login_url")
    if not login_url:
        raise ValueError("login_url must be provided in credentials")
        
    await page.goto(login_url, wait_until="networkidle")
    
    # 2. Fill fields using credentials dict
    await page.fill("#username", credentials.get("username", ""))
    await page.fill("#password", credentials.get("password", ""))
    
    # 3. Click submit
    await page.click("#submit-btn")
    
    # 4. Wait for dashboard main to verify login
    await page.wait_for_selector("#dashboard-main", state="visible", timeout=5000)
    logger.info("Mock custom login script completed successfully.")
