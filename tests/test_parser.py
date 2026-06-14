import unittest
from src.parser import clean_html, get_content_hash, generate_diff

class TestParser(unittest.TestCase):
    def test_clean_html_basic(self):
        html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <h1>Header</h1>
                <script>alert(1);</script>
                <style>body { color: red; }</style>
                <p>Hello World</p>
                <!-- Comment -->
            </body>
        </html>
        """
        cleaned = clean_html(html)
        # Verify script/style tags and comments are removed, and text is cleaned
        self.assertIn("Header", cleaned)
        self.assertIn("Hello World", cleaned)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("body {", cleaned)
        self.assertNotIn("Comment", cleaned)
        # It should extract just the text lines
        self.assertEqual(cleaned, "Header\nHello World")

    def test_clean_html_selector(self):
        html = """
        <div id="sidebar">Sidebar Content</div>
        <div id="main">
            <p>Main Article Content</p>
        </div>
        """
        cleaned = clean_html(html, selector="#main")
        self.assertEqual(cleaned, "Main Article Content")
        
        # Test raising error for missing selector
        with self.assertRaises(ValueError):
            clean_html(html, selector="#missing")

    def test_clean_html_exclude(self):
        html = """
        <div id="content">
            <p class="announcement">Important news</p>
            <p class="timestamp">Posted at 12:00 PM</p>
            <p class="timestamp">Updated at 12:15 PM</p>
        </div>
        """
        # Clean with exclude selector
        cleaned = clean_html(html, selector="#content", exclude_selectors=[".timestamp"])
        self.assertEqual(cleaned, "Important news")

    def test_get_content_hash(self):
        text1 = "Hello World"
        text2 = "Hello World"
        text3 = "Hello World!"
        
        hash1 = get_content_hash(text1)
        hash2 = get_content_hash(text2)
        hash3 = get_content_hash(text3)
        
        self.assertEqual(hash1, hash2)
        self.assertNotEqual(hash1, hash3)

    def test_generate_diff(self):
        old_text = "Line 1\nLine 2\nLine 3"
        new_text = "Line 1\nLine 2 changed\nLine 3"
        
        diff = generate_diff(old_text, new_text)
        self.assertIn("-Line 2", diff)
        self.assertIn("+Line 2 changed", diff)

if __name__ == "__main__":
    unittest.main()
