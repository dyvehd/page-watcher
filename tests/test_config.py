import unittest
import os
import yaml
from src.config import load_config, AppConfig

class TestConfig(unittest.TestCase):
    def setUp(self):
        self.test_config_path = "test_config_temp.yaml"
        self.mock_config = {
            "discord_webhook_url": "https://discord.com/api/webhooks/mock",
            "check_interval_seconds": 600,
            "groups": {
                "group1": {
                    "name": "Test Group 1",
                    "login": {
                        "type": "recipe",
                        "recipe": [
                            {"action": "navigate", "url": "http://example.com/login"},
                            {"action": "fill", "selector": "#username", "value": "testuser"},
                            {"action": "click", "selector": "#btn"}
                        ]
                    },
                    "pages": [
                        {
                            "key": "page1",
                            "name": "Test Page 1",
                            "url": "http://example.com/page1",
                            "selector": "#content",
                            "exclude": [".time"],
                            "check_interval_seconds": 300
                        }
                    ]
                }
            }
        }
        with open(self.test_config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.mock_config, f)

    def tearDown(self):
        if os.path.exists(self.test_config_path):
            os.remove(self.test_config_path)

    def test_load_valid_config(self):
        config = load_config(self.test_config_path)
        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.discord_webhook_url, "https://discord.com/api/webhooks/mock")
        self.assertEqual(config.check_interval_seconds, 600)
        self.assertIn("group1", config.groups)
        
        group = config.groups["group1"]
        self.assertEqual(group.name, "Test Group 1")
        self.assertEqual(group.login.type, "recipe")
        self.assertEqual(len(group.login.recipe), 3)
        self.assertEqual(group.login.recipe[0].action, "navigate")
        
        self.assertEqual(len(group.pages), 1)
        page = group.pages[0]
        self.assertEqual(page.key, "page1")
        self.assertEqual(page.url, "http://example.com/page1")
        self.assertEqual(page.selector, "#content")
        self.assertEqual(page.exclude, [".time"])
        self.assertEqual(page.check_interval_seconds, 300)

    def test_invalid_action_raises(self):
        # Change action to an invalid value
        self.mock_config["groups"]["group1"]["login"]["recipe"][0]["action"] = "invalid_action"
        with open(self.test_config_path, "w") as f:
            yaml.dump(self.mock_config, f)
            
        with self.assertRaises(Exception):
            load_config(self.test_config_path)

if __name__ == "__main__":
    unittest.main()
