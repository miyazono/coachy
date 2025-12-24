"""Activity classification using rules-based and optional LLM backends."""
import logging
import re
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from ..storage.models import CATEGORIES

logger = logging.getLogger(__name__)


class ClassifierError(Exception):
    """Exception raised when classification fails."""
    pass


class ActivityClassifier:
    """Classifies activities based on app, window, and text content."""
    
    def __init__(self, backend: str = "rules"):
        """Initialize classifier with specified backend.
        
        Args:
            backend: Classification backend ("rules", "local_llm", or "anthropic")
        """
        self.backend = backend
        self.categories = CATEGORIES
        
    def classify(
        self,
        app_name: Optional[str],
        window_title: Optional[str], 
        ocr_text: Optional[str] = None
    ) -> str:
        """Classify activity into a category.
        
        Args:
            app_name: Name of the active application
            window_title: Title of the active window
            ocr_text: Text extracted from screenshot (optional)
            
        Returns:
            Category name from CATEGORIES keys
        """
        if self.backend == "rules":
            return self._classify_rules(app_name, window_title, ocr_text)
        elif self.backend == "local_llm":
            return self._classify_local_llm(app_name, window_title, ocr_text)
        elif self.backend == "anthropic":
            return self._classify_anthropic(app_name, window_title, ocr_text)
        else:
            logger.warning(f"Unknown classifier backend: {self.backend}")
            return "unknown"
    
    def _classify_rules(
        self,
        app_name: Optional[str],
        window_title: Optional[str],
        ocr_text: Optional[str] = None
    ) -> str:
        """Classify using rules-based pattern matching.
        
        This is the default, zero-token classification method.
        """
        # Normalize inputs
        app_name = (app_name or "").lower()
        window_title = (window_title or "").lower()
        ocr_text = (ocr_text or "").lower()
        
        # 1. First check app name against category signals
        for category, config in self.categories.items():
            for signal in config["signals"]:
                if signal.lower() in app_name:
                    logger.debug(f"Classified as {category} based on app: {signal}")
                    return category
        
        # 2. Check window title for URL patterns and specific keywords
        category = self._classify_by_window_title(window_title)
        if category != "unknown":
            return category
        
        # 3. Check OCR text for additional signals
        if ocr_text:
            category = self._classify_by_ocr_text(ocr_text)
            if category != "unknown":
                return category
        
        # 4. Special application-specific rules
        category = self._classify_app_specific_rules(app_name, window_title)
        if category != "unknown":
            return category
        
        logger.debug(f"No classification rule matched for app='{app_name}', window='{window_title}'")
        return "unknown"
    
    def _classify_by_window_title(self, window_title: str) -> str:
        """Classify based on window title patterns."""
        if not window_title:
            return "unknown"
        
        # Social media domains
        social_domains = ["twitter.com", "x.com", "linkedin.com", "reddit.com", 
                         "news.ycombinator.com", "facebook.com", "instagram.com"]
        for domain in social_domains:
            if domain in window_title:
                logger.debug(f"Classified as social_media based on domain: {domain}")
                return "social_media"
        
        # Video/entertainment domains
        entertainment_domains = ["youtube.com", "netflix.com", "twitch.tv", 
                               "spotify.com", "apple music"]
        for domain in entertainment_domains:
            if domain in window_title:
                logger.debug(f"Classified as break based on domain: {domain}")
                return "break"
        
        # Development/coding patterns
        dev_patterns = ["github.com", "stack overflow", "gitlab", "bitbucket",
                       "localhost:", "127.0.0.1", "dev server", "webpack"]
        for pattern in dev_patterns:
            if pattern in window_title:
                logger.debug(f"Classified as deep_work based on dev pattern: {pattern}")
                return "deep_work"
        
        # Communication patterns
        comm_patterns = ["gmail", "mail", "email", "slack", "discord", "teams"]
        for pattern in comm_patterns:
            if pattern in window_title:
                logger.debug(f"Classified as communication based on pattern: {pattern}")
                return "communication"
        
        # Meeting/video call patterns
        meeting_patterns = ["zoom meeting", "google meet", "microsoft teams", 
                          "webex", "facetime", "call"]
        for pattern in meeting_patterns:
            if pattern in window_title:
                logger.debug(f"Classified as meetings based on pattern: {pattern}")
                return "meetings"
        
        return "unknown"
    
    def _classify_by_ocr_text(self, ocr_text: str) -> str:
        """Classify based on OCR text content."""
        if not ocr_text or len(ocr_text) < 20:  # Too little text to be useful
            return "unknown"
        
        # Code/development indicators
        code_patterns = [
            r'\bdef \w+\(',           # Python function definitions
            r'\bfunction \w+\(',      # JavaScript functions
            r'\bclass \w+\b',         # Class definitions
            r'\bimport \w+',          # Import statements
            r'\b(git|npm|pip|cargo)\s+\w+',  # Command line tools
            r'\b(localhost|127\.0\.0\.1)',   # Local development
            r'\{[^}]*\}',             # Code blocks with braces
            r'^\s*\w+\s*=\s*\w+',    # Variable assignments
        ]
        
        for pattern in code_patterns:
            if re.search(pattern, ocr_text, re.MULTILINE | re.IGNORECASE):
                logger.debug(f"Classified as deep_work based on code pattern")
                return "deep_work"
        
        # Email/communication indicators
        email_patterns = [
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',  # Email addresses
            r'\bsubject:\s*\w+',      # Email subjects
            r'\binbox\b',             # Email inbox
            r'\breply\b.*\bto\b',     # Email replies
            r'\bmessage\s+from\b',    # Messages
        ]
        
        for pattern in email_patterns:
            if re.search(pattern, ocr_text, re.IGNORECASE):
                logger.debug(f"Classified as communication based on email pattern")
                return "communication"
        
        # Writing/documentation indicators
        writing_patterns = [
            r'\b(chapter|section|paragraph)\s+\d+',  # Document structure
            r'\b(title|heading|abstract)\b:',        # Document parts
            r'\b(draft|manuscript|paper|article)\b', # Writing types
            r'\b\d+\s+(words|characters)\b',         # Word counts
        ]
        
        for pattern in writing_patterns:
            if re.search(pattern, ocr_text, re.IGNORECASE):
                logger.debug(f"Classified as deep_work based on writing pattern")
                return "deep_work"
        
        return "unknown"
    
    def _classify_app_specific_rules(self, app_name: str, window_title: str) -> str:
        """Apply app-specific classification rules."""
        
        # Browser-specific rules based on window titles
        browsers = ["chrome", "safari", "firefox", "arc", "edge"]
        if any(browser in app_name for browser in browsers):
            # If it's a browser, classify based on content not app name
            if any(pattern in window_title for pattern in 
                   ["github", "stack overflow", "documentation", "docs"]):
                return "research"
            elif any(pattern in window_title for pattern in 
                     ["twitter", "facebook", "reddit", "youtube"]):
                return "social_media"
        
        # Terminal/command line applications
        terminals = ["terminal", "iterm", "kitty", "alacritty", "console"]
        if any(term in app_name for term in terminals):
            return "deep_work"
        
        # Text editors and IDEs
        editors = ["vim", "emacs", "nano", "code", "xcode", "intellij", "pycharm",
                   "sublime", "atom", "notepad"]
        if any(editor in app_name for editor in editors):
            return "deep_work"
        
        # Design tools
        design_tools = ["figma", "sketch", "photoshop", "illustrator", "canva"]
        if any(tool in app_name for tool in design_tools):
            return "deep_work"
        
        # Note-taking and writing
        writing_tools = ["obsidian", "notion", "roam", "logseq", "bear", "ulysses",
                        "scrivener", "typora", "mark", "markdown"]
        if any(tool in app_name for tool in writing_tools):
            return "deep_work"
        
        # File managers
        file_managers = ["finder", "explorer", "nautilus", "dolphin"]
        if any(fm in app_name for fm in file_managers):
            return "administrative"
        
        return "unknown"
    
    def _classify_local_llm(
        self,
        app_name: Optional[str],
        window_title: Optional[str],
        ocr_text: Optional[str] = None
    ) -> str:
        """Classify using local LLM (not implemented in Phase 2)."""
        logger.warning("Local LLM classification not implemented yet, falling back to rules")
        return self._classify_rules(app_name, window_title, ocr_text)
    
    def _classify_anthropic(
        self,
        app_name: Optional[str],
        window_title: Optional[str], 
        ocr_text: Optional[str] = None
    ) -> str:
        """Classify using Anthropic API (not implemented in Phase 2)."""
        logger.warning("Anthropic classification not implemented yet, falling back to rules")
        return self._classify_rules(app_name, window_title, ocr_text)
    
    def get_category_info(self, category: str) -> Dict[str, Any]:
        """Get information about a category.
        
        Args:
            category: Category name
            
        Returns:
            Dictionary with category information
        """
        return self.categories.get(category, {
            "description": "Unknown category",
            "signals": []
        })
    
    def get_all_categories(self) -> Dict[str, Dict[str, Any]]:
        """Get all available categories and their information."""
        return self.categories.copy()


def classify_activity(
    app_name: Optional[str],
    window_title: Optional[str],
    ocr_text: Optional[str] = None,
    backend: str = "rules"
) -> str:
    """Convenience function to classify an activity.
    
    Args:
        app_name: Name of the active application
        window_title: Title of the active window
        ocr_text: Text extracted from screenshot
        backend: Classification backend to use
        
    Returns:
        Category name
    """
    classifier = ActivityClassifier(backend)
    return classifier.classify(app_name, window_title, ocr_text)


if __name__ == "__main__":
    # Test the classifier with some examples
    test_cases = [
        ("VS Code", "main.py - myproject", None),
        ("Chrome", "GitHub - microsoft/vscode", None),
        ("Slack", "general | MyCompany Slack", None),
        ("Zoom", "Meeting with John Smith", None),
        ("Chrome", "Twitter", None),
        ("Finder", "Documents", None),
        ("Terminal", "bash", "$ git status\n$ python main.py"),
    ]
    
    classifier = ActivityClassifier("rules")
    
    print("Classification Test Results")
    print("=" * 50)
    
    for app, window, ocr in test_cases:
        category = classifier.classify(app, window, ocr)
        print(f"App: {app:12} | Window: {window:25} | Category: {category}")
    
    print(f"\nAvailable categories: {list(classifier.get_all_categories().keys())}")