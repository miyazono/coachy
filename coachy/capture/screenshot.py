"""Screenshot capture using macOS Quartz framework."""
import logging
import pathlib
import time
from typing import Optional

try:
    import Quartz
    from PIL import Image
    QUARTZ_AVAILABLE = True
except ImportError:
    QUARTZ_AVAILABLE = False

logger = logging.getLogger(__name__)


class ScreenshotError(Exception):
    """Exception raised when screenshot capture fails."""
    pass


def capture_screenshot(
    monitor: str = "primary",
    output_path: Optional[str] = None,
    quality: int = 85
) -> str:
    """Capture screenshot and save as JPEG.
    
    Args:
        monitor: Monitor to capture ("primary", "all", or specific ID)
        output_path: Path to save screenshot. If None, generates unique filename
        quality: JPEG quality (1-100)
        
    Returns:
        Path to saved screenshot file
        
    Raises:
        ScreenshotError: If capture fails
    """
    if not QUARTZ_AVAILABLE:
        raise ScreenshotError("Quartz framework not available - macOS required")
    
    # Generate filename if not provided
    if output_path is None:
        timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
        # Default to data/screenshots directory
        output_path = pathlib.Path("data/screenshots") / f"screenshot_{timestamp}.jpg"
    else:
        output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Capture screenshot based on monitor setting
        if monitor == "primary":
            # Capture primary display only
            screenshot = _capture_primary_display()
        elif monitor == "all":
            # Capture all displays as single image
            screenshot = _capture_all_displays()
        else:
            # Capture specific display (for future expansion)
            screenshot = _capture_primary_display()
            logger.warning(f"Specific monitor selection not implemented, using primary")
        
        # Save as JPEG with specified quality
        _save_as_jpeg(screenshot, output_path, quality)
        
        logger.debug(f"Screenshot saved: {output_path}")
        return str(output_path)
        
    except Exception as e:
        raise ScreenshotError(f"Failed to capture screenshot: {e}") from e


def _capture_primary_display():
    """Capture the primary display."""
    # Get main display ID
    main_display_id = Quartz.CGMainDisplayID()
    
    # Create image of the main display
    region = Quartz.CGRectInfinite  # Capture entire display
    image_ref = Quartz.CGDisplayCreateImage(main_display_id)
    
    if image_ref is None:
        raise ScreenshotError("Failed to create display image")
    
    return image_ref


def _capture_all_displays():
    """Capture all displays as a single image."""
    # For now, just capture primary display
    # Future enhancement: stitch multiple displays together
    return _capture_primary_display()


def _save_as_jpeg(image_ref, output_path: pathlib.Path, quality: int) -> None:
    """Save CGImage as JPEG file.
    
    Args:
        image_ref: CGImageRef from Quartz
        output_path: Output file path
        quality: JPEG quality (1-100)
    """
    # Convert CGImage to PIL Image for saving
    width = Quartz.CGImageGetWidth(image_ref)
    height = Quartz.CGImageGetHeight(image_ref)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(image_ref)
    
    # Get raw pixel data
    data_provider = Quartz.CGImageGetDataProvider(image_ref)
    pixel_data = Quartz.CGDataProviderCopyData(data_provider)
    
    # Create PIL Image from raw data
    try:
        # Convert to PIL Image
        pil_image = Image.frombuffer(
            "RGBA", (width, height), pixel_data, "raw", "BGRA", bytes_per_row, 1
        )
        
        # Convert RGBA to RGB for JPEG (JPEG doesn't support transparency)
        if pil_image.mode == "RGBA":
            rgb_image = Image.new("RGB", pil_image.size, (255, 255, 255))
            rgb_image.paste(pil_image, mask=pil_image.split()[-1])
            pil_image = rgb_image
        
        # Save as JPEG with specified quality
        pil_image.save(str(output_path), "JPEG", quality=quality, optimize=True)

    finally:
        # Note: Do NOT call CFRelease on image_ref - pyobjc manages
        # reference counting automatically. Calling CFRelease causes
        # a double-free crash (SIGSEGV/exit code 139).
        pass


def get_display_info() -> dict:
    """Get information about available displays.
    
    Returns:
        Dictionary with display information
    """
    if not QUARTZ_AVAILABLE:
        return {"error": "Quartz framework not available"}
    
    try:
        main_display_id = Quartz.CGMainDisplayID()
        bounds = Quartz.CGDisplayBounds(main_display_id)
        
        return {
            "main_display_id": int(main_display_id),
            "width": int(bounds.size.width),
            "height": int(bounds.size.height),
            "x": int(bounds.origin.x),
            "y": int(bounds.origin.y),
        }
    except Exception as e:
        logger.error(f"Failed to get display info: {e}")
        return {"error": str(e)}