"""Tests for Phase 6: Spatial Window-Aware OCR.

Tests coordinate conversion, window matching, and the spatial mapping pipeline.
"""
import sys
import unittest

# ---------------------------------------------------------------------------
# Coordinate conversion tests (pure math — no macOS dependencies)
# ---------------------------------------------------------------------------

from coachy.process.spatial import (
    WindowOCRResult,
    vision_bbox_to_screen,
    map_ocr_to_windows,
)
from coachy.process.ocr import OCRTextBlock
from coachy.capture.windows import VisibleWindow


class TestVisionBboxToScreen(unittest.TestCase):
    """Test the Vision → screen coordinate conversion."""

    def test_identity_no_retina(self):
        """1:1 mapping when image and screen are the same size."""
        # Vision bbox at bottom-left quarter of a 1000x1000 image/screen
        # vx=0, vy=0, vw=0.5, vh=0.5  →  left half, bottom half
        # In screen coords (top-left origin) that's left half, top half flipped
        sx, sy, sw, sh = vision_bbox_to_screen(
            (0.0, 0.0, 0.5, 0.5), 1000, 1000, 1000, 1000
        )
        self.assertAlmostEqual(sx, 0.0)
        self.assertAlmostEqual(sy, 500.0)  # flipped: bottom half → y=500
        self.assertAlmostEqual(sw, 500.0)
        self.assertAlmostEqual(sh, 500.0)

    def test_top_right_corner(self):
        """Vision top-right should map to screen top-right."""
        # Vision: origin bottom-left, so top-right = (0.75, 0.75, 0.25, 0.25)
        sx, sy, sw, sh = vision_bbox_to_screen(
            (0.75, 0.75, 0.25, 0.25), 2000, 2000, 1000, 1000
        )
        # image pixels: px=1500, py=1500, pw=500, ph=500
        # flip Y: py_top = 2000 - (1500+500) = 0
        # scale: 1000/2000 = 0.5  → sx=750, sy=0, sw=250, sh=250
        self.assertAlmostEqual(sx, 750.0)
        self.assertAlmostEqual(sy, 0.0)
        self.assertAlmostEqual(sw, 250.0)
        self.assertAlmostEqual(sh, 250.0)

    def test_retina_2x(self):
        """Retina 2x: image is 2x the screen size."""
        # Full-screen block in Vision coords
        sx, sy, sw, sh = vision_bbox_to_screen(
            (0.0, 0.0, 1.0, 1.0), 2880, 1800, 1440, 900
        )
        self.assertAlmostEqual(sx, 0.0)
        self.assertAlmostEqual(sy, 0.0)
        self.assertAlmostEqual(sw, 1440.0)
        self.assertAlmostEqual(sh, 900.0)

    def test_center_block(self):
        """A block centred in the image maps to the centre of the screen."""
        sx, sy, sw, sh = vision_bbox_to_screen(
            (0.25, 0.25, 0.5, 0.5), 1000, 1000, 1000, 1000
        )
        self.assertAlmostEqual(sx, 250.0)
        self.assertAlmostEqual(sy, 250.0)
        self.assertAlmostEqual(sw, 500.0)
        self.assertAlmostEqual(sh, 500.0)


class TestMapOcrToWindows(unittest.TestCase):
    """Test mapping OCR blocks to windows."""

    def _make_window(self, app, title, pid, bounds, wid=1):
        return VisibleWindow(
            app_name=app,
            window_title=title,
            owner_pid=pid,
            bounds=bounds,
            layer=0,
            window_id=wid,
        )

    def _make_block(self, text, vision_bbox, confidence=0.9):
        return OCRTextBlock(text=text, bbox=vision_bbox, confidence=confidence)

    def test_single_window_captures_all(self):
        """All blocks inside one full-screen window."""
        win = self._make_window("VS Code", "main.py", 100, (0, 0, 1000, 1000), wid=1)
        # Block at centre of screen (vision coords centre)
        block = self._make_block("hello world", (0.4, 0.4, 0.2, 0.2))

        results = map_ocr_to_windows(
            [block], [win],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
            focused_pid=100,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].app_name, "VS Code")
        self.assertTrue(results[0].focused)
        self.assertIn("hello world", results[0].ocr_text)

    def test_two_windows_frontmost_wins(self):
        """Overlapping windows: frontmost (first in list) gets the block."""
        front = self._make_window("Chrome", "docs", 200, (0, 0, 600, 1000), wid=1)
        back = self._make_window("Terminal", "bash", 300, (0, 0, 1000, 1000), wid=2)
        # Block at x=300 centre — inside both windows
        block = self._make_block("api docs", (0.25, 0.4, 0.1, 0.1))

        results = map_ocr_to_windows(
            [block], [front, back],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        # Chrome is frontmost and should get the block
        chrome_results = [r for r in results if r.app_name == "Chrome"]
        self.assertEqual(len(chrome_results), 1)
        self.assertIn("api docs", chrome_results[0].ocr_text)

    def test_block_outside_all_windows(self):
        """Block outside all windows goes to 'Other' bucket."""
        win = self._make_window("VS Code", "main.py", 100, (0, 0, 500, 500), wid=1)
        # Block in bottom-right of screen — outside the 500x500 window
        # Vision (0.8, 0.0, 0.1, 0.1) → screen: px=800, flip y → top=900
        block = self._make_block("menu bar text", (0.8, 0.0, 0.1, 0.1))

        results = map_ocr_to_windows(
            [block], [win],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        other = [r for r in results if r.app_name == "Other"]
        self.assertEqual(len(other), 1)
        self.assertIn("menu bar text", other[0].ocr_text)

    def test_empty_windows_list(self):
        """No windows → empty result."""
        block = self._make_block("orphan", (0.5, 0.5, 0.1, 0.1))
        results = map_ocr_to_windows(
            [block], [],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        self.assertEqual(results, [])

    def test_empty_blocks_list(self):
        """No blocks → no results (window with no text is skipped)."""
        win = self._make_window("VS Code", "main.py", 100, (0, 0, 1000, 1000), wid=1)
        results = map_ocr_to_windows(
            [], [win],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        self.assertEqual(results, [])

    def test_screen_percentage(self):
        """Screen percentage calculated correctly."""
        # Window covers exactly 25% of screen
        win = self._make_window("App", "Win", 100, (0, 0, 500, 500), wid=1)
        block = self._make_block("text", (0.2, 0.6, 0.1, 0.1))

        results = map_ocr_to_windows(
            [block], [win],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0].screen_percentage, 25.0, places=1)

    def test_text_truncation(self):
        """Per-window text is capped at 2000 chars."""
        win = self._make_window("App", "Win", 100, (0, 0, 1000, 1000), wid=1)
        # Generate a block with lots of text
        long_text = "x" * 2500
        block = self._make_block(long_text, (0.4, 0.4, 0.2, 0.2))

        results = map_ocr_to_windows(
            [block], [win],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
        )
        self.assertLessEqual(len(results[0].ocr_text), 2000)

    def test_focused_pid_marking(self):
        """focused=True only for window matching focused_pid."""
        w1 = self._make_window("VS Code", "main.py", 100, (0, 0, 500, 1000), wid=1)
        w2 = self._make_window("Chrome", "docs", 200, (500, 0, 500, 1000), wid=2)

        b1 = self._make_block("code", (0.2, 0.4, 0.1, 0.1))
        b2 = self._make_block("web", (0.7, 0.4, 0.1, 0.1))

        results = map_ocr_to_windows(
            [b1, b2], [w1, w2],
            screen_w=1000, screen_h=1000,
            image_w=1000, image_h=1000,
            focused_pid=100,
        )
        vscode = [r for r in results if r.app_name == "VS Code"][0]
        chrome = [r for r in results if r.app_name == "Chrome"][0]
        self.assertTrue(vscode.focused)
        self.assertFalse(chrome.focused)


class TestWindowOCRResultSerialization(unittest.TestCase):
    """Test WindowOCRResult.to_metadata_dict()."""

    def test_round_trip(self):
        result = WindowOCRResult(
            app_name="VS Code",
            window_title="daemon.py - coachy",
            focused=True,
            screen_percentage=30.123456,
            ocr_text="def foo():",
            ocr_char_count=10,
        )
        d = result.to_metadata_dict()
        self.assertEqual(d["app_name"], "VS Code")
        self.assertTrue(d["focused"])
        self.assertEqual(d["screen_percentage"], 30.1)  # rounded


# ---------------------------------------------------------------------------
# Integration test: window enumeration (requires macOS)
# ---------------------------------------------------------------------------

class TestWindowEnumeration(unittest.TestCase):
    """Test get_visible_windows() on real macOS."""

    def test_returns_list(self):
        """Should return a list (possibly empty in CI)."""
        from coachy.capture.windows import get_visible_windows, QUARTZ_AVAILABLE
        if not QUARTZ_AVAILABLE:
            self.skipTest("Quartz not available")
        windows = get_visible_windows()
        self.assertIsInstance(windows, list)
        # On a real desktop there should be at least one window
        if windows:
            self.assertTrue(windows[0].app_name)
            self.assertGreater(windows[0].bounds[2], 0)  # width > 0

    def test_screen_dimensions(self):
        """get_screen_dimensions returns positive values on macOS."""
        from coachy.capture.windows import get_screen_dimensions, QUARTZ_AVAILABLE
        if not QUARTZ_AVAILABLE:
            self.skipTest("Quartz not available")
        w, h = get_screen_dimensions()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)


if __name__ == "__main__":
    unittest.main()
