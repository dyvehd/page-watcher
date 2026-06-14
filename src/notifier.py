import logging
import json
import os
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_change_notification(
        self,
        group_name: str,
        page_name: str,
        url: str,
        diff_summary: str,
        screenshot_path: Optional[str] = None
    ) -> bool:
        """
        Sends a Discord notification with a premium layout containing a title,
        description, line-by-line diff, and optional screenshot image.
        """
        # Truncate diff to fit inside Discord embed field limit (1024 chars)
        max_diff_len = 950
        if len(diff_summary) > max_diff_len:
            truncated_diff = diff_summary[:max_diff_len] + "\n... [diff truncated due to size] ..."
        else:
            truncated_diff = diff_summary

        embed = {
            "title": f"✨ Change Detected: {page_name}",
            "description": f"The monitored page in group **{group_name}** has changed.",
            "url": url,
            "color": 5763719,  # Vibrant green
            "fields": [
                {
                    "name": "URL",
                    "value": url,
                    "inline": False
                },
                {
                    "name": "Diff Preview",
                    "value": f"```diff\n{truncated_diff}\n```" if truncated_diff else "*Empty diff (structural change only)*",
                    "inline": False
                }
            ],
            "footer": {
                "text": "Page Watcher Service"
            }
        }

        files = {}
        if screenshot_path and os.path.exists(screenshot_path):
            embed["image"] = {"url": "attachment://screenshot.png"}
            
            try:
                # We open the file and add it to the files dict
                # Note: The file descriptor will be closed after the post request block
                f = open(screenshot_path, "rb")
                files["file1"] = ("screenshot.png", f, "image/png")
            except Exception as e:
                logger.error(f"Failed to open screenshot file for attachment: {e}")

        # Construct the multipart payload
        payload = {"embeds": [embed]}
        files["payload_json"] = (None, json.dumps(payload), "application/json")

        try:
            async with httpx.AsyncClient() as client:
                # Send multipart request
                response = await client.post(self.webhook_url, files=files, timeout=20.0)
                
                # Check for success
                if response.status_code in (200, 204):
                    logger.info(f"Successfully sent Discord notification for {page_name}.")
                    return True
                else:
                    logger.error(f"Discord webhook failed with status code {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Error sending Discord notification: {e}")
            return False
        finally:
            # Explicitly close any open file handlers we passed
            if "file1" in files:
                try:
                    files["file1"][1].close()
                except Exception:
                    pass

    async def send_error_notification(self, group_name: str, page_name: str, error_msg: str) -> bool:
        """Sends an alert notification to Discord when a check fails (e.g. login expired or selector missing)."""
        embed = {
            "title": f"⚠️ Monitor Failure: {page_name}",
            "description": f"An error occurred while running checks for **{page_name}** in group **{group_name}**.",
            "color": 15548997,  # Vibrant red
            "fields": [
                {
                    "name": "Error Message",
                    "value": f"```\n{error_msg}\n```",
                    "inline": False
                }
            ],
            "footer": {
                "text": "Page Watcher Service"
            }
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    headers={"Content-Type": "application/json"},
                    timeout=10.0
                )
                return response.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Error sending error notification: {e}")
            return False
