import hashlib
import difflib
from typing import List, Optional
from bs4 import BeautifulSoup, Comment

def clean_html(html_content: str, selector: Optional[str] = None, exclude_selectors: Optional[List[str]] = None) -> str:
    """
    Parses HTML, filters it by selector (if provided), prunes excluded elements,
    removes non-content tags, and extracts clean normalized text.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # If selector is specified, extract the target subtree
    if selector:
        target = soup.select_one(selector)
        if not target:
            # If selector isn't found, raise ValueError to indicate parsing issue
            # (which helps detect login page redirects or page structural changes)
            raise ValueError(f"Target selector '{selector}' was not found in the page.")
        # Replace the soup with the target element
        soup = BeautifulSoup(str(target), "html.parser")

    # Remove script, style, SVG, etc.
    tags_to_remove = ["script", "style", "noscript", "svg", "iframe", "link", "meta", "form", "head"]
    for tag in soup.find_all(tags_to_remove):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(text=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove exclude selectors
    if exclude_selectors:
        for ex_sel in exclude_selectors:
            for element in soup.select(ex_sel):
                element.decompose()

    # Extract clean text with newline separation
    text_content = soup.get_text(separator="\n")
    
    # Clean up empty lines and normalize whitespace
    lines = []
    for line in text_content.splitlines():
        cleaned_line = " ".join(line.split()).strip()
        if cleaned_line:
            lines.append(cleaned_line)
            
    return "\n".join(lines)

def get_content_hash(text: str) -> str:
    """Calculate SHA-256 hash of text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def generate_diff(old_text: str, new_text: str, n_context_lines: int = 3) -> str:
    """
    Generate unified diff between old_text and new_text.
    Returns empty string if no differences.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="previous_state",
        tofile="current_state",
        lineterm="",
        n=n_context_lines
    )
    
    return "\n".join(diff)
