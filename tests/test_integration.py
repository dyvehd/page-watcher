import unittest
import asyncio
import os
import shutil
import sys
from datetime import datetime

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.config import AppConfig, GroupConfig, PageConfig, LoginConfig, LoginRecipeStep
from src.database import Database
from src.browser import BrowserManager
from src.parser import clean_html, get_content_hash, generate_diff
from tests import mock_server

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start mock server
        cls.server_port = 8089
        cls.server = mock_server.run_server(port=cls.server_port)
        cls.base_url = f"http://localhost:{cls.server_port}"
        
        # Reset announcement
        mock_server.announcement_text = "Initial announcement: No classes next Monday!"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.db_path = "test_integration.db"
        self.screenshots_dir = "test_screenshots"
        self.db = Database(self.db_path)
        
        # Reset announcement
        mock_server.announcement_text = "Initial announcement: No classes next Monday!"
        
        # Clean screenshots from previous runs
        if os.path.exists(self.screenshots_dir):
            shutil.rmtree(self.screenshots_dir)

    def tearDown(self):
        # Clean up database and screenshots
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        if os.path.exists(self.screenshots_dir):
            try:
                shutil.rmtree(self.screenshots_dir)
            except OSError:
                pass

    def test_full_crawler_and_login_flow(self):
        # Create an async helper to run the tests in the event loop
        async def run_test():
            # Setup configurations
            login_config = LoginConfig(
                type="recipe",
                recipe=[
                    LoginRecipeStep(action="navigate", url=f"{self.base_url}/login"),
                    LoginRecipeStep(action="fill", selector="#username", value="student_user"),
                    LoginRecipeStep(action="fill", selector="#password", value="secure_password_123"),
                    LoginRecipeStep(action="click", selector="#submit-btn"),
                    LoginRecipeStep(action="wait_for", selector="#dashboard-main")
                ]
            )
            
            page_config = PageConfig(
                key="dashboard",
                name="LMS Dashboard",
                url=f"{self.base_url}/dashboard",
                selector=".announcement-content",
                exclude=[]
            )
            
            # 1. Verify standard Playwright (or Camoufox) browser runs and performs login
            # We disable Camoufox here if we are running in unit tests where only standard playwright is pre-configured
            # But the browser manager automatically falls back if camoufox isn't fully set up yet.
            bm = BrowserManager(use_camoufox=False)
            
            # Fetch the page first time (should run login recipe)
            html_content, screenshot_path = await bm.fetch_page(
                group_key="test_group",
                page_config=page_config,
                login_config=login_config,
                db=self.db,
                screenshots_dir=self.screenshots_dir
            )
            
            # Verify screenshot was generated
            self.assertTrue(os.path.exists(screenshot_path))
            
            # Verify page text was extracted correctly
            cleaned = clean_html(html_content, selector=page_config.selector)
            self.assertEqual(cleaned, "Initial announcement: No classes next Monday!")
            
            # 2. Verify cookies were captured and saved to database
            cookies, _ = self.db.get_group_session("test_group")
            self.assertIsNotNone(cookies)
            # Find the session_token cookie
            token_cookie = next((c for c in cookies if c["name"] == "session_token"), None)
            self.assertIsNotNone(token_cookie)
            self.assertEqual(token_cookie["value"], "valid_token")
            
            # 3. Fetch again (should NOT run login recipe, should load cookies directly)
            # We modify the login credentials in the recipe to invalid values. If it runs the recipe, it will fail.
            # If it uses the cookies, it should succeed directly.
            bad_login_config = LoginConfig(
                type="recipe",
                recipe=[
                    LoginRecipeStep(action="navigate", url=f"{self.base_url}/login"),
                    LoginRecipeStep(action="fill", selector="#username", value="wrong_user"),
                    LoginRecipeStep(action="fill", selector="#password", value="wrong_password"),
                    LoginRecipeStep(action="click", selector="#submit-btn"),
                    LoginRecipeStep(action="wait_for", selector="#dashboard-main")
                ]
            )
            
            html_content2, screenshot_path2 = await bm.fetch_page(
                group_key="test_group",
                page_config=page_config,
                login_config=bad_login_config,
                db=self.db,
                screenshots_dir=self.screenshots_dir
            )
            
            cleaned2 = clean_html(html_content2, selector=page_config.selector)
            self.assertEqual(cleaned2, "Initial announcement: No classes next Monday!")
            
            # 4. Simulate a page content change in mock server
            mock_server.announcement_text = "Updated announcement: Exam is rescheduled to Friday!"
            
            # Fetch once more
            html_content3, screenshot_path3 = await bm.fetch_page(
                group_key="test_group",
                page_config=page_config,
                login_config=bad_login_config,
                db=self.db,
                screenshots_dir=self.screenshots_dir
            )
            
            cleaned3 = clean_html(html_content3, selector=page_config.selector)
            self.assertEqual(cleaned3, "Updated announcement: Exam is rescheduled to Friday!")
            
            # Generate diff
            diff = generate_diff(cleaned2, cleaned3)
            self.assertIn("-Initial announcement", diff)
            self.assertIn("+Updated announcement", diff)

        asyncio.run(run_test())

    def test_custom_script_login_flow(self):
        async def run_test():
            script_path = os.path.join(os.path.dirname(__file__), "mock_custom_login.py")
            
            login_config = LoginConfig(
                type="script",
                script_path=script_path,
                credentials={
                    "username": "student_user",
                    "password": "secure_password_123",
                    "login_url": f"{self.base_url}/login"
                }
            )
            
            page_config = PageConfig(
                key="dashboard_script",
                name="LMS Dashboard (Script)",
                url=f"{self.base_url}/dashboard",
                selector=".announcement-content",
                exclude=[]
            )
            
            bm = BrowserManager(use_camoufox=False)
            
            # Reset announcement for test consistency
            mock_server.announcement_text = "Script announcement: Active!"
            
            # Fetch the page first time (should dynamically load and run mock_custom_login.py)
            html_content, screenshot_path = await bm.fetch_page(
                group_key="test_group_script",
                page_config=page_config,
                login_config=login_config,
                db=self.db,
                screenshots_dir=self.screenshots_dir
            )
            
            self.assertTrue(os.path.exists(screenshot_path))
            
            cleaned = clean_html(html_content, selector=page_config.selector)
            self.assertEqual(cleaned, "Script announcement: Active!")
            
            # Verify cookies were saved
            cookies, _ = self.db.get_group_session("test_group_script")
            self.assertIsNotNone(cookies)
            token_cookie = next((c for c in cookies if c["name"] == "session_token"), None)
            self.assertIsNotNone(token_cookie)
            self.assertEqual(token_cookie["value"], "valid_token")

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
