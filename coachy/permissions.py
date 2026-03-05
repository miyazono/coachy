"""Screen Recording permission check for macOS.

Attempts a minimal Quartz screen capture to determine whether the app has
Screen Recording permission. If the capture returns a null image (all-zero
or None), permission has not been granted.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from Quartz import (
        CGWindowListCreateImage,
        CGRectMake,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
        kCGWindowImageDefault,
    )
    _QUARTZ_AVAILABLE = True
except ImportError:
    _QUARTZ_AVAILABLE = False


def check_screen_recording_permission() -> bool:
    """Test whether Screen Recording permission is granted.

    Captures a tiny 1x1 region of the screen. If the system returns a valid
    image, permission is granted. If it returns None, the user hasn't enabled
    the permission in System Settings.

    Returns:
        True if the app can capture the screen.
    """
    if not _QUARTZ_AVAILABLE:
        logger.warning("Quartz framework not available — cannot check Screen Recording")
        return False

    try:
        image = CGWindowListCreateImage(
            CGRectMake(0, 0, 1, 1),
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
            kCGWindowImageDefault,
        )
        if image is None:
            logger.info("Screen Recording permission not granted")
            return False
        return True
    except Exception as e:
        logger.warning(f"Screen Recording permission check failed: {e}")
        return False
