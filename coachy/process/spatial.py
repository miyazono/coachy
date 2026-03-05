"""Spatial mapping of OCR text blocks to visible windows."""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..capture.windows import VisibleWindow
from .ocr import OCRTextBlock

logger = logging.getLogger(__name__)

# Maximum chars of OCR text to store per window
_MAX_TEXT_PER_WINDOW = 2000


@dataclass
class WindowOCRResult:
    """OCR text mapped to a specific visible window."""
    app_name: str
    window_title: str
    focused: bool
    screen_percentage: float
    ocr_text: str
    ocr_char_count: int

    def to_metadata_dict(self) -> Dict[str, Any]:
        """Serialize for storage in ActivityEntry.metadata['windows']."""
        return {
            "app_name": self.app_name,
            "window_title": self.window_title,
            "focused": self.focused,
            "screen_percentage": round(self.screen_percentage, 1),
            "ocr_text": self.ocr_text,
            "ocr_char_count": self.ocr_char_count,
        }


def vision_bbox_to_screen(
    vision_bbox: Tuple[float, float, float, float],
    image_w: int,
    image_h: int,
    screen_w: int,
    screen_h: int,
) -> Tuple[float, float, float, float]:
    """Convert a Vision normalized bounding box to screen-point coordinates.

    Vision coordinates are normalized 0-1 with origin at bottom-left.
    Screen coordinates are in points with origin at top-left.

    On Retina displays the screenshot image may have more pixels than screen
    points, so we use ``screen_w / image_w`` as the scale factor.

    Args:
        vision_bbox: (vx, vy, vw, vh) in normalized Vision coords.
        image_w: Screenshot width in pixels.
        image_h: Screenshot height in pixels.
        screen_w: Display width in screen points.
        screen_h: Display height in screen points.

    Returns:
        (sx, sy, sw, sh) in screen points, top-left origin.
    """
    vx, vy, vw, vh = vision_bbox

    # Step 1: normalized → image pixels
    px = vx * image_w
    py = vy * image_h
    pw = vw * image_w
    ph = vh * image_h

    # Step 2: flip Y (bottom-left → top-left origin)
    py_top = image_h - (py + ph)

    # Step 3: image pixels → screen points
    scale_x = screen_w / image_w if image_w else 1.0
    scale_y = screen_h / image_h if image_h else 1.0

    sx = px * scale_x
    sy = py_top * scale_y
    sw = pw * scale_x
    sh = ph * scale_y

    return (sx, sy, sw, sh)


def map_ocr_to_windows(
    ocr_blocks: List[OCRTextBlock],
    visible_windows: List[VisibleWindow],
    screen_w: int,
    screen_h: int,
    image_w: int,
    image_h: int,
    focused_pid: Optional[int] = None,
) -> List[WindowOCRResult]:
    """Assign each OCR text block to the frontmost window containing its center.

    Args:
        ocr_blocks: Text blocks from extract_text_blocks().
        visible_windows: Windows from get_visible_windows() (front-to-back order).
        screen_w: Display width in screen points.
        screen_h: Display height in screen points.
        image_w: Screenshot width in pixels.
        image_h: Screenshot height in pixels.
        focused_pid: PID of the focused application (to mark ``focused=True``).

    Returns:
        List of WindowOCRResult, one per window that received text, plus an
        optional "Other" entry for text outside all windows.
    """
    if not visible_windows:
        return []

    screen_area = screen_w * screen_h if (screen_w and screen_h) else 1.0

    # Prepare per-window accumulators keyed by window_id
    win_texts: Dict[int, List[str]] = {}
    for win in visible_windows:
        win_texts[win.window_id] = []

    other_texts: List[str] = []

    for block in ocr_blocks:
        sx, sy, sw, sh = vision_bbox_to_screen(
            block.bbox, image_w, image_h, screen_w, screen_h
        )
        # Center of the text block in screen points
        cx = sx + sw / 2.0
        cy = sy + sh / 2.0

        matched = False
        # Iterate front-to-back; first containing window wins
        for win in visible_windows:
            wx, wy, ww, wh = win.bounds
            if wx <= cx <= wx + ww and wy <= cy <= wy + wh:
                win_texts[win.window_id].append(block.text)
                matched = True
                break

        if not matched:
            other_texts.append(block.text)

    # Build results
    results: List[WindowOCRResult] = []

    for win in visible_windows:
        texts = win_texts[win.window_id]
        if not texts:
            # Still include the window with empty OCR if it's the focused one
            if focused_pid is not None and win.owner_pid == focused_pid:
                pass  # fall through to add it
            else:
                continue

        combined = "\n".join(texts)
        if len(combined) > _MAX_TEXT_PER_WINDOW:
            combined = combined[:_MAX_TEXT_PER_WINDOW]

        wx, wy, ww, wh = win.bounds
        win_area = ww * wh
        screen_pct = min((win_area / screen_area) * 100.0, 100.0)

        results.append(WindowOCRResult(
            app_name=win.app_name,
            window_title=win.window_title,
            focused=(focused_pid is not None and win.owner_pid == focused_pid),
            screen_percentage=screen_pct,
            ocr_text=combined,
            ocr_char_count=len(combined),
        ))

    # Collect "Other" bucket if any
    if other_texts:
        combined_other = "\n".join(other_texts)
        if len(combined_other) > _MAX_TEXT_PER_WINDOW:
            combined_other = combined_other[:_MAX_TEXT_PER_WINDOW]
        results.append(WindowOCRResult(
            app_name="Other",
            window_title="",
            focused=False,
            screen_percentage=0.0,
            ocr_text=combined_other,
            ocr_char_count=len(combined_other),
        ))

    return results
