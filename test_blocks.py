"""Tests for the Activity Block Builder and Privacy Scrubber."""
import json
import time
import unittest
from unittest.mock import MagicMock, patch

from coachy.coach.blocks import (
    ActivityBlock,
    ActivityBlockBuilder,
    ActivityBlockFormatter,
    ActivityTimeline,
)
from coachy.coach.privacy_scrubber import PrivacyScrubber
from coachy.process.classifier import ActivityClassifier


# ---------------------------------------------------------------------------
# Helpers to build fake DB rows
# ---------------------------------------------------------------------------

def _make_row(
    ts, app="VS Code", title="main.py - project", category="deep_work",
    duration=60, change_ratio=0.15, is_idle=False, windows=None,
    ocr_text="some code here",
):
    """Build a fake DB row dict as returned by get_activity_metadata_timeline."""
    inference = {
        "activity_type": "idle" if is_idle else "active_work",
        "change_ratio": change_ratio,
    }
    if is_idle:
        inference["idle_duration_captures"] = 5

    meta = {"processing": inference}
    if windows is not None:
        meta["windows"] = windows

    return {
        "id": ts,
        "timestamp": ts,
        "app_name": app,
        "window_title": title,
        "category": category,
        "duration_seconds": duration,
        "metadata": meta,
    }


def _ts(hour, minute=0):
    """Return a Unix timestamp for today at the given hour:minute."""
    import datetime
    dt = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Block grouping tests
# ---------------------------------------------------------------------------

class TestBlockGrouping(unittest.TestCase):
    """Test that captures are grouped into blocks correctly."""

    def setUp(self):
        self.builder = ActivityBlockBuilder(capture_interval=60)

    def test_same_window_forms_one_block(self):
        rows = [
            _make_row(_ts(9, 0)),
            _make_row(_ts(9, 1)),
            _make_row(_ts(9, 2)),
        ]
        timeline = self.builder.build_timeline(rows)
        self.assertEqual(len(timeline.blocks), 1)
        self.assertEqual(timeline.blocks[0].capture_count, 3)

    def test_different_window_splits_blocks(self):
        rows = [
            _make_row(_ts(9, 0), app="VS Code", title="main.py"),
            _make_row(_ts(9, 1), app="VS Code", title="main.py"),
            _make_row(_ts(9, 2), app="Chrome", title="GitHub"),
            _make_row(_ts(9, 3), app="Chrome", title="GitHub"),
        ]
        timeline = self.builder.build_timeline(rows)
        self.assertEqual(len(timeline.blocks), 2)
        self.assertEqual(timeline.blocks[0].app_name, "VS Code")
        self.assertEqual(timeline.blocks[1].app_name, "Chrome")

    def test_time_gap_splits_blocks(self):
        rows = [
            _make_row(_ts(9, 0)),
            _make_row(_ts(9, 1)),
            # 5-minute gap (> 2.5 * 60s threshold)
            _make_row(_ts(9, 6)),
            _make_row(_ts(9, 7)),
        ]
        timeline = self.builder.build_timeline(rows)
        self.assertEqual(len(timeline.blocks), 2)

    def test_idle_break_splits_blocks(self):
        rows = [
            _make_row(_ts(9, 0)),
            _make_row(_ts(9, 1), is_idle=True),
            _make_row(_ts(9, 2), is_idle=True),
            _make_row(_ts(9, 3), is_idle=True),
            _make_row(_ts(9, 4)),
        ]
        timeline = self.builder.build_timeline(rows)
        self.assertGreaterEqual(len(timeline.blocks), 2)

    def test_empty_rows(self):
        timeline = self.builder.build_timeline([])
        self.assertEqual(len(timeline.blocks), 0)
        self.assertEqual(timeline.total_active_minutes, 0)

    def test_single_capture_block(self):
        rows = [_make_row(_ts(9, 0))]
        timeline = self.builder.build_timeline(rows)
        self.assertEqual(len(timeline.blocks), 1)
        self.assertEqual(timeline.blocks[0].capture_count, 1)
        self.assertGreaterEqual(timeline.blocks[0].duration_minutes, 1)


# ---------------------------------------------------------------------------
# Active window identification tests
# ---------------------------------------------------------------------------

class TestActiveWindowIdentification(unittest.TestCase):
    """Test that the correct window is identified as 'active'."""

    def setUp(self):
        self.builder = ActivityBlockBuilder(capture_interval=60)

    def test_focused_window_with_high_change_wins(self):
        windows = [
            {"app_name": "VS Code", "window_title": "main.py", "focused": True,
             "ocr_text": "code", "screen_percentage": 60},
            {"app_name": "Chrome", "window_title": "Docs", "focused": False,
             "ocr_text": "docs", "screen_percentage": 40},
        ]
        row = _make_row(_ts(9, 0), windows=windows, change_ratio=0.2)
        # Add per_window_changes to processing metadata
        row["metadata"]["processing"]["per_window_changes"] = [
            {"app_name": "VS Code", "window_title": "main.py", "change_ratio": 0.2},
            {"app_name": "Chrome", "window_title": "Docs", "change_ratio": 0.05},
        ]

        enriched = self.builder._identify_active_window(row)
        self.assertEqual(enriched["active_app"], "VS Code")

    def test_highest_change_window_when_focused_idle(self):
        windows = [
            {"app_name": "Arc", "window_title": "Tara tab", "focused": True,
             "ocr_text": "static", "screen_percentage": 50},
            {"app_name": "VS Code", "window_title": "editor", "focused": False,
             "ocr_text": "lots of typing", "screen_percentage": 50},
        ]
        row = _make_row(_ts(9, 0), windows=windows, change_ratio=0.01)
        row["metadata"]["processing"]["per_window_changes"] = [
            {"app_name": "Arc", "window_title": "Tara tab", "change_ratio": 0.005},
            {"app_name": "VS Code", "window_title": "editor", "change_ratio": 0.25},
        ]

        enriched = self.builder._identify_active_window(row)
        self.assertEqual(enriched["active_app"], "VS Code")

    def test_fallback_to_os_reported(self):
        """No window metadata → falls back to row's app_name."""
        row = _make_row(_ts(9, 0), app="Terminal", title="bash")
        enriched = self.builder._identify_active_window(row)
        self.assertEqual(enriched["active_app"], "Terminal")

    def test_no_window_metadata_pre_phase6(self):
        """Pre-Phase 6 rows have no windows key in metadata."""
        row = {
            "id": 1, "timestamp": _ts(9, 0), "app_name": "Finder",
            "window_title": "Documents", "category": "administrative",
            "duration_seconds": 60, "metadata": {"processing": {}},
        }
        enriched = self.builder._identify_active_window(row)
        self.assertEqual(enriched["active_app"], "Finder")


# ---------------------------------------------------------------------------
# Context extraction tests
# ---------------------------------------------------------------------------

class TestContextExtraction(unittest.TestCase):
    """Test app-specific context extraction."""

    def setUp(self):
        self.builder = ActivityBlockBuilder()

    def test_email_context(self):
        label, _ = self.builder._extract_context(
            "Mail", "Re: Project Update - Mail", ["Subject: Q4 Budget Review"]
        )
        self.assertIn("email", label.lower())

    def test_browser_context(self):
        label, _ = self.builder._extract_context(
            "Chrome", "React Docs - Google Chrome", []
        )
        self.assertIn("React Docs", label)

    def test_editor_context(self):
        label, _ = self.builder._extract_context(
            "VS Code", "spatial.py - coachy — Visual Studio Code", []
        )
        self.assertIn("spatial.py", label)

    def test_chat_context(self):
        label, _ = self.builder._extract_context(
            "Slack", "#engineering | Company Slack", []
        )
        self.assertIn("#engineering", label)

    def test_generic_fallback(self):
        label, _ = self.builder._extract_context(
            "SomeApp", "Some Window Title", []
        )
        self.assertTrue(len(label) > 0)


# ---------------------------------------------------------------------------
# Privacy scrubber tests
# ---------------------------------------------------------------------------

class TestPrivacyScrubberRegex(unittest.TestCase):
    """Test the regex-based privacy scrubber."""

    def test_scrub_emails(self):
        text = "email to john@example.com about project"
        result = PrivacyScrubber._scrub_with_regex(text)
        self.assertNotIn("john@example.com", result)
        self.assertIn("[email]", result)

    def test_scrub_phone_numbers(self):
        text = "Call me at 555-123-4567 tomorrow"
        result = PrivacyScrubber._scrub_with_regex(text)
        self.assertNotIn("555-123-4567", result)
        self.assertIn("[phone]", result)

    def test_scrub_urls(self):
        text = "See https://internal.company.com/secret-project for details"
        result = PrivacyScrubber._scrub_with_regex(text)
        self.assertNotIn("internal.company.com", result)
        self.assertIn("[url]", result)

    def test_scrub_file_paths(self):
        text = "editing /Users/evan/secret-project/main.py"
        result = PrivacyScrubber._scrub_with_regex(text)
        self.assertNotIn("/Users/evan", result)
        self.assertIn("[path]", result)

    def test_preserve_app_names(self):
        text = "VS Code: editing file (30min, high engagement)"
        result = PrivacyScrubber._scrub_with_regex(text)
        self.assertIn("VS Code", result)
        self.assertIn("30min", result)

    def test_empty_text(self):
        scrubber = PrivacyScrubber.__new__(PrivacyScrubber)
        scrubber._config = MagicMock()
        scrubber._config.get = MagicMock(return_value="regex")
        scrubber._mode = "regex"
        scrubber._prompt_template = ""
        scrubber._local_client = None
        self.assertEqual(scrubber.scrub(""), "")
        self.assertEqual(scrubber.scrub("   "), "   ")


# ---------------------------------------------------------------------------
# Timeline formatting tests
# ---------------------------------------------------------------------------

class TestTimelineFormatting(unittest.TestCase):
    """Test that timeline formatting stays within token budget."""

    def test_format_empty_timeline(self):
        timeline = ActivityTimeline(
            blocks=[], total_active_minutes=0, total_idle_minutes=0,
            context_switches=0, top_apps={}, time_range="",
        )
        text = ActivityBlockFormatter.format_for_prompt(timeline)
        self.assertIn("No activity data", text)

    def test_format_typical_day(self):
        """30 blocks should produce ~600-800 tokens of output."""
        blocks = []
        base = _ts(9, 0)
        for i in range(30):
            blocks.append(ActivityBlock(
                start_time=base + i * 1800,
                end_time=base + (i + 1) * 1800,
                duration_minutes=25,
                app_name="VS Code" if i % 3 else "Chrome",
                window_title=f"file_{i}.py",
                activity_label=f"editing file_{i}.py" if i % 3 else f"reading docs page {i}",
                activity_type="active_work",
                avg_change_ratio=0.15,
                capture_count=5,
            ))

        timeline = ActivityTimeline(
            blocks=blocks, total_active_minutes=750, total_idle_minutes=30,
            context_switches=15, top_apps={"VS Code": 500, "Chrome": 250},
            time_range="09:00-18:00",
        )

        text = ActivityBlockFormatter.format_for_prompt(timeline)
        # Rough token estimate: ~4 chars per token
        estimated_tokens = len(text) // 4
        self.assertLess(estimated_tokens, 1200, f"Too many tokens: {estimated_tokens}")
        self.assertIn("Activity Timeline", text)

    def test_weekly_filters_short_blocks(self):
        blocks = [
            ActivityBlock(
                start_time=_ts(9, 0), end_time=_ts(9, 2),
                duration_minutes=2, app_name="Finder", window_title="docs",
                activity_label="browsing files", activity_type="reading",
                avg_change_ratio=0.05, capture_count=2,
            ),
            ActivityBlock(
                start_time=_ts(9, 5), end_time=_ts(10, 0),
                duration_minutes=55, app_name="VS Code", window_title="main.py",
                activity_label="editing main.py", activity_type="active_work",
                avg_change_ratio=0.2, capture_count=55,
            ),
        ]

        timeline = ActivityTimeline(
            blocks=blocks, total_active_minutes=57, total_idle_minutes=0,
            context_switches=1, top_apps={"VS Code": 55}, time_range="09:00-10:00",
        )

        text = ActivityBlockFormatter.format_for_prompt(timeline, period="week")
        # The 2-minute block should be filtered out
        self.assertNotIn("browsing files", text)
        self.assertIn("editing main.py", text)


# ---------------------------------------------------------------------------
# Classifier browser fix tests
# ---------------------------------------------------------------------------

class TestClassifierBrowserFix(unittest.TestCase):
    """Verify that browsers are classified by content, not app name."""

    def setUp(self):
        self.classifier = ActivityClassifier("rules")

    def test_firefox_gmail_is_communication(self):
        result = self.classifier.classify("Firefox", "Inbox - Gmail", None)
        self.assertEqual(result, "communication")

    def test_chrome_github_is_deep_work(self):
        result = self.classifier.classify("Chrome", "Issues - github.com/org/repo", None)
        self.assertEqual(result, "deep_work")

    def test_arc_twitter_is_social_media(self):
        result = self.classifier.classify("Arc", "Home / x.com", None)
        self.assertEqual(result, "social_media")

    def test_safari_youtube_is_break(self):
        result = self.classifier.classify("Safari", "Funny video - youtube.com", None)
        self.assertEqual(result, "break")

    def test_chrome_generic_is_research(self):
        """Unknown browser page defaults to research."""
        result = self.classifier.classify("Chrome", "Some Random Page", None)
        self.assertEqual(result, "research")

    def test_chrome_docs_is_deep_work(self):
        result = self.classifier.classify("Chrome", "Untitled - docs.google.com", None)
        self.assertEqual(result, "deep_work")

    def test_non_browser_unchanged(self):
        """Non-browser apps still classify by signals."""
        result = self.classifier.classify("VS Code", "main.py - project", None)
        self.assertEqual(result, "deep_work")

        result = self.classifier.classify("Slack", "general | Company", None)
        self.assertEqual(result, "communication")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases and regression tests."""

    def test_none_metadata(self):
        """Rows with None metadata should not crash."""
        builder = ActivityBlockBuilder()
        row = {
            "id": 1, "timestamp": _ts(9, 0), "app_name": "App",
            "window_title": "Win", "category": "unknown",
            "duration_seconds": 60, "metadata": None,
        }
        enriched = builder._identify_active_window(row)
        self.assertEqual(enriched["active_app"], "App")

    def test_title_normalization(self):
        builder = ActivityBlockBuilder()
        self.assertEqual(
            builder._normalize_title("main.py — Visual Studio Code"),
            "main.py"
        )
        self.assertEqual(
            builder._normalize_title("React Docs - Google Chrome"),
            "React Docs"
        )
        self.assertEqual(
            builder._normalize_title(""),
            ""
        )

    def test_display_format(self):
        """Smoke test for CLI display format."""
        blocks = [ActivityBlock(
            start_time=_ts(9, 0), end_time=_ts(10, 0),
            duration_minutes=60, app_name="VS Code", window_title="main.py",
            activity_label="editing main.py", activity_type="active_work",
            avg_change_ratio=0.18, capture_count=60,
        )]
        timeline = ActivityTimeline(
            blocks=blocks, total_active_minutes=60, total_idle_minutes=0,
            context_switches=0, top_apps={"VS Code": 60}, time_range="09:00-10:00",
        )
        text = ActivityBlockFormatter.format_for_display(timeline)
        self.assertIn("VS Code", text)
        self.assertIn("editing main.py", text)


if __name__ == "__main__":
    unittest.main()
