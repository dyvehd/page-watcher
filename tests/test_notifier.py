import unittest
from unittest.mock import AsyncMock, patch
import os
import json
from src.notifier import DiscordNotifier

class TestDiscordNotifier(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.webhook_url = "https://discord.com/api/webhooks/mock_test"
        self.notifier = DiscordNotifier(self.webhook_url)

    @patch("httpx.AsyncClient.post")
    async def test_send_change_notification_short_diff(self, mock_post):
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        diff_summary = "Line 1 added\nLine 2 removed"
        
        success = await self.notifier.send_change_notification(
            group_name="TestGroup",
            page_name="TestPage",
            url="http://example.com",
            diff_summary=diff_summary
        )

        self.assertTrue(success)
        mock_post.assert_called_once()
        
        # Check files argument passed to httpx.AsyncClient.post
        call_kwargs = mock_post.call_args[1]
        self.assertIn("files", call_kwargs)
        files = call_kwargs["files"]
        
        self.assertIn("payload_json", files)
        self.assertNotIn("file2", files) # No attachment for short diffs
        
        # Verify JSON payload structure
        payload = json.loads(files["payload_json"][1])
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "✨ Change Detected: TestPage")
        self.assertIn("TestGroup", embed["description"])
        self.assertEqual(embed["fields"][1]["value"], f"```diff\n{diff_summary}\n```")

    @patch("httpx.AsyncClient.post")
    async def test_send_change_notification_long_diff(self, mock_post):
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        # Generate a diff that exceeds 950 characters
        diff_summary = "A" * 1000
        
        success = await self.notifier.send_change_notification(
            group_name="TestGroup",
            page_name="TestPage",
            url="http://example.com",
            diff_summary=diff_summary
        )

        self.assertTrue(success)
        mock_post.assert_called_once()
        
        call_kwargs = mock_post.call_args[1]
        self.assertIn("files", call_kwargs)
        files = call_kwargs["files"]
        
        self.assertIn("payload_json", files)
        self.assertIn("file2", files) # Attachment should be present
        
        # Check attachment content
        filename, data, content_type = files["file2"]
        self.assertEqual(filename, "diff.txt")
        self.assertEqual(data, diff_summary.encode("utf-8"))
        self.assertEqual(content_type, "text/plain")

        # Verify JSON payload structure shows truncation message
        payload = json.loads(files["payload_json"][1])
        embed = payload["embeds"][0]
        preview_val = embed["fields"][1]["value"]
        self.assertIn("[diff truncated - see attached diff.txt]", preview_val)

if __name__ == "__main__":
    unittest.main()
