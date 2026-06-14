import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import os
import asyncio
from src.config import AppConfig, GroupConfig, PageConfig, LoginConfig
from src.scheduler import WatcherScheduler

class TestSchedulerRetry(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create a mock config
        self.config = AppConfig(
            discord_webhook_url="http://mock-webhook",
            check_interval_seconds=60,
            save_screenshots=False,
            error_retry_threshold=3,
            groups={}
        )
        # We will patch the Database and BrowserManager to avoid real file / browser operations
        self.db_patch = patch("src.scheduler.Database")
        self.mock_db_class = self.db_patch.start()
        self.mock_db = MagicMock()
        self.mock_db_class.return_value = self.mock_db
        
        self.browser_patch = patch("src.scheduler.BrowserManager")
        self.mock_browser_class = self.browser_patch.start()
        self.mock_browser = MagicMock()
        self.mock_browser_class.return_value = self.mock_browser

    def tearDown(self):
        self.db_patch.stop()
        self.browser_patch.stop()

    async def test_error_retry_threshold(self):
        # Setup page and group configs
        page_config = PageConfig(key="testpage", name="Test Page", url="http://example.com/page")
        group_config = GroupConfig(
            name="Test Group",
            login=LoginConfig(type="none"),
            pages=[page_config]
        )
        
        # Instantiate scheduler
        scheduler = WatcherScheduler(self.config, db_path=":memory:")
        
        # Mock notifier
        scheduler.notifier = AsyncMock()
        
        # Make fetch_page throw an exception to simulate check failure
        scheduler.browser_mgr.fetch_page = AsyncMock(side_effect=ValueError("Connection reset by peer"))
        
        # 1st failure: should not send error notification
        await scheduler.check_page("testgroup", group_config, page_config)
        scheduler.notifier.send_error_notification.assert_not_called()
        self.assertEqual(scheduler.failure_counts[("testgroup", "testpage")], 1)
        
        # 2nd failure: should not send error notification
        await scheduler.check_page("testgroup", group_config, page_config)
        scheduler.notifier.send_error_notification.assert_not_called()
        self.assertEqual(scheduler.failure_counts[("testgroup", "testpage")], 2)
        
        # 3rd failure: should send error notification
        await scheduler.check_page("testgroup", group_config, page_config)
        scheduler.notifier.send_error_notification.assert_called_once_with(
            group_name="Test Group",
            page_name="Test Page (3 consecutive failures)",
            error_msg="Connection reset by peer"
        )
        self.assertEqual(scheduler.failure_counts[("testgroup", "testpage")], 3)
        self.assertIn(("testgroup", "testpage"), scheduler.failed_pages)
        
        # 4th failure: should NOT send another notification since error msg is unchanged
        scheduler.notifier.send_error_notification.reset_mock()
        await scheduler.check_page("testgroup", group_config, page_config)
        scheduler.notifier.send_error_notification.assert_not_called()
        self.assertEqual(scheduler.failure_counts[("testgroup", "testpage")], 4)
        
        # Success run: should reset consecutive failures and clear active failure state
        scheduler.browser_mgr.fetch_page = AsyncMock(return_value=("<html>Test</html>", None))
        scheduler.db.get_last_page_state.return_value = {"id": 1, "content_hash": "hash", "cleaned_content": "Test"}
        
        # Run success check
        await scheduler.check_page("testgroup", group_config, page_config)
        self.assertEqual(scheduler.failure_counts[("testgroup", "testpage")], 0)
        self.assertNotIn(("testgroup", "testpage"), scheduler.failed_pages)

if __name__ == "__main__":
    unittest.main()
