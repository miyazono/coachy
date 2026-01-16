"""Screenshot diff and activity inference based on OCR changes."""
import logging
from difflib import SequenceMatcher
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ActivityInference:
    """Infers user activity based on comparing consecutive screenshots."""

    # Thresholds for activity detection
    IDLE_THRESHOLD = 0.02  # Less than 2% change = idle/reading
    MINOR_CHANGE_THRESHOLD = 0.10  # 2-10% = light activity (scrolling, clicking)
    ACTIVE_THRESHOLD = 0.30  # 10-30% = active work (typing, editing)
    # Above 30% = major change (app switch, new document, etc.)

    def __init__(self):
        """Initialize the activity inference engine."""
        self.previous_ocr_text: Optional[str] = None
        self.previous_app_name: Optional[str] = None
        self.previous_window_title: Optional[str] = None
        self.idle_count: int = 0  # Track consecutive idle captures

    def analyze(
        self,
        current_ocr_text: Optional[str],
        current_app_name: Optional[str],
        current_window_title: Optional[str]
    ) -> Dict[str, Any]:
        """Analyze current capture against previous to infer activity.

        Args:
            current_ocr_text: OCR text from current screenshot
            current_app_name: Current active application
            current_window_title: Current window title

        Returns:
            Dictionary with inference results:
            - activity_type: idle, reading, light_activity, active_work, context_switch, new_session
            - confidence: 0.0 to 1.0
            - change_ratio: how much the screen changed
            - inferred_action: human-readable description
            - is_productive: whether the time should count as productive
        """
        result = {
            "activity_type": "unknown",
            "confidence": 0.0,
            "change_ratio": 0.0,
            "inferred_action": "",
            "is_productive": True,
            "idle_duration_captures": 0
        }

        # First capture of session
        if self.previous_ocr_text is None:
            result["activity_type"] = "new_session"
            result["inferred_action"] = "Started new session"
            result["confidence"] = 1.0
            self._update_previous(current_ocr_text, current_app_name, current_window_title)
            return result

        # Check for app/window change
        app_changed = current_app_name != self.previous_app_name
        window_changed = current_window_title != self.previous_window_title

        if app_changed:
            result["activity_type"] = "context_switch"
            result["inferred_action"] = f"Switched from {self.previous_app_name} to {current_app_name}"
            result["confidence"] = 1.0
            result["change_ratio"] = 1.0
            self.idle_count = 0
            self._update_previous(current_ocr_text, current_app_name, current_window_title)
            return result

        # Compare OCR text
        change_ratio = self._calculate_change_ratio(
            self.previous_ocr_text or "",
            current_ocr_text or ""
        )
        result["change_ratio"] = change_ratio

        # Infer activity based on change ratio
        if change_ratio < self.IDLE_THRESHOLD:
            self.idle_count += 1
            result["activity_type"] = "idle"
            result["idle_duration_captures"] = self.idle_count
            result["is_productive"] = False

            if self.idle_count >= 3:
                result["inferred_action"] = f"Idle/away for {self.idle_count} captures - likely stepped away"
                result["confidence"] = 0.9
            else:
                result["inferred_action"] = "Reading or thinking (no screen changes)"
                result["confidence"] = 0.7
                result["is_productive"] = True  # Short idle = reading

        elif change_ratio < self.MINOR_CHANGE_THRESHOLD:
            self.idle_count = 0
            result["activity_type"] = "reading"
            result["inferred_action"] = "Light activity (scrolling, navigation, or reading)"
            result["confidence"] = 0.8
            result["is_productive"] = True

        elif change_ratio < self.ACTIVE_THRESHOLD:
            self.idle_count = 0
            result["activity_type"] = "active_work"
            result["inferred_action"] = "Active work (typing, editing, or interacting)"
            result["confidence"] = 0.85
            result["is_productive"] = True

        else:
            self.idle_count = 0
            result["activity_type"] = "major_change"
            if window_changed:
                result["inferred_action"] = f"Switched context within {current_app_name}"
            else:
                result["inferred_action"] = "Major screen change (new document, page, or view)"
            result["confidence"] = 0.75
            result["is_productive"] = True

        self._update_previous(current_ocr_text, current_app_name, current_window_title)
        return result

    def _calculate_change_ratio(self, text1: str, text2: str) -> float:
        """Calculate how much the text changed between captures.

        Uses SequenceMatcher to find similarity, returns 1 - similarity
        so higher values mean more change.

        Args:
            text1: Previous OCR text
            text2: Current OCR text

        Returns:
            Change ratio from 0.0 (identical) to 1.0 (completely different)
        """
        if not text1 and not text2:
            return 0.0
        if not text1 or not text2:
            return 1.0

        # Normalize texts for comparison
        text1_normalized = self._normalize_text(text1)
        text2_normalized = self._normalize_text(text2)

        similarity = SequenceMatcher(
            None,
            text1_normalized,
            text2_normalized
        ).quick_ratio()

        return 1.0 - similarity

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison.

        Removes extra whitespace and converts to lowercase.
        """
        return ' '.join(text.lower().split())

    def _update_previous(
        self,
        ocr_text: Optional[str],
        app_name: Optional[str],
        window_title: Optional[str]
    ) -> None:
        """Update previous state for next comparison."""
        self.previous_ocr_text = ocr_text
        self.previous_app_name = app_name
        self.previous_window_title = window_title

    def reset(self) -> None:
        """Reset the inference state (e.g., after screen lock)."""
        self.previous_ocr_text = None
        self.previous_app_name = None
        self.previous_window_title = None
        self.idle_count = 0
        logger.debug("Activity inference state reset")


def test_activity_inference():
    """Test the activity inference with sample data."""
    print("Testing Activity Inference")
    print("=" * 50)

    inference = ActivityInference()

    test_cases = [
        # First capture
        ("Hello world, this is a document.", "VS Code", "main.py"),
        # Same content = idle
        ("Hello world, this is a document.", "VS Code", "main.py"),
        # Minor change = reading/scrolling
        ("Hello world, this is a document. More text.", "VS Code", "main.py"),
        # Significant change = active work
        ("def hello():\n    print('world')\n    return True", "VS Code", "main.py"),
        # App switch
        ("Inbox - 5 new messages", "Mail", "Inbox"),
        # Back to code
        ("def hello():\n    print('world')", "VS Code", "main.py"),
    ]

    for i, (ocr, app, title) in enumerate(test_cases):
        result = inference.analyze(ocr, app, title)
        print(f"\n{i+1}. App: {app}, Title: {title}")
        print(f"   Type: {result['activity_type']}")
        print(f"   Action: {result['inferred_action']}")
        print(f"   Change: {result['change_ratio']:.1%}")
        print(f"   Productive: {result['is_productive']}")


if __name__ == "__main__":
    test_activity_inference()
