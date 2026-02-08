"""Visible window enumeration using macOS Quartz CGWindowList API."""
import logging
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

try:
    import Quartz
    QUARTZ_AVAILABLE = True
except ImportError:
    QUARTZ_AVAILABLE = False

logger = logging.getLogger(__name__)

# System processes that don't represent user-visible windows
_DEFAULT_EXCLUDE_APPS = frozenset({
    "Window Server", "SystemUIServer", "Control Centre", "Control Center",
    "Dock", "Spotlight", "Notification Center", "NotificationCenter",
    "WindowManager",
})


@dataclass
class VisibleWindow:
    """A visible on-screen window with its spatial bounds."""
    app_name: str
    window_title: str
    owner_pid: int
    bounds: Tuple[float, float, float, float]  # (x, y, w, h) screen points, top-left origin
    layer: int
    window_id: int


def get_visible_windows(
    min_size: int = 100,
    exclude_apps: Optional[Set[str]] = None,
) -> List[VisibleWindow]:
    """Get all on-screen windows on the current Space, ordered front-to-back.

    Args:
        min_size: Minimum width and height in screen points to include.
        exclude_apps: App names to exclude. Defaults to system UI processes.

    Returns:
        List of VisibleWindow ordered front-to-back (frontmost first).
    """
    if not QUARTZ_AVAILABLE:
        logger.warning("Quartz framework not available — cannot enumerate windows")
        return []

    if exclude_apps is None:
        exclude_apps = _DEFAULT_EXCLUDE_APPS

    try:
        # Get on-screen windows, excluding desktop elements
        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID,
        )
        if not window_list:
            return []

        # Get primary display bounds for filtering
        primary_bounds = _get_primary_display_bounds()

        windows = []
        for win_dict in window_list:
            layer = win_dict.get(Quartz.kCGWindowLayer, -1)
            # Only layer-0 windows are normal app windows
            if layer != 0:
                continue

            app_name = win_dict.get(Quartz.kCGWindowOwnerName, "")
            if not app_name or app_name in exclude_apps:
                continue

            bounds_dict = win_dict.get(Quartz.kCGWindowBounds, {})
            x = float(bounds_dict.get("X", 0))
            y = float(bounds_dict.get("Y", 0))
            w = float(bounds_dict.get("Width", 0))
            h = float(bounds_dict.get("Height", 0))

            # Skip windows smaller than min_size
            if w < min_size or h < min_size:
                continue

            # Filter to windows overlapping the primary display
            if primary_bounds is not None:
                px, py, pw, ph = primary_bounds
                if x + w <= px or x >= px + pw or y + h <= py or y >= py + ph:
                    continue

            window_title = win_dict.get(Quartz.kCGWindowName, "") or ""
            owner_pid = int(win_dict.get(Quartz.kCGWindowOwnerPID, 0))
            window_id = int(win_dict.get(Quartz.kCGWindowNumber, 0))

            windows.append(VisibleWindow(
                app_name=app_name,
                window_title=window_title,
                owner_pid=owner_pid,
                bounds=(x, y, w, h),
                layer=layer,
                window_id=window_id,
            ))

        logger.debug(f"Enumerated {len(windows)} visible windows")
        return windows

    except Exception as e:
        logger.error(f"Failed to enumerate windows: {e}")
        return []


def get_screen_dimensions() -> Tuple[int, int]:
    """Get primary display dimensions in screen points.

    Returns:
        (width, height) in screen points, or (0, 0) if unavailable.
    """
    if not QUARTZ_AVAILABLE:
        return (0, 0)

    try:
        main_id = Quartz.CGMainDisplayID()
        bounds = Quartz.CGDisplayBounds(main_id)
        return (int(bounds.size.width), int(bounds.size.height))
    except Exception as e:
        logger.error(f"Failed to get screen dimensions: {e}")
        return (0, 0)


def _get_primary_display_bounds() -> Optional[Tuple[float, float, float, float]]:
    """Get primary display bounds as (x, y, width, height)."""
    try:
        main_id = Quartz.CGMainDisplayID()
        bounds = Quartz.CGDisplayBounds(main_id)
        return (
            float(bounds.origin.x),
            float(bounds.origin.y),
            float(bounds.size.width),
            float(bounds.size.height),
        )
    except Exception:
        return None
