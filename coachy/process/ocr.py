"""Text extraction using macOS Vision framework."""
import logging
import pathlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import Vision
    import Quartz
    from Foundation import NSURL
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Exception raised when OCR processing fails."""
    pass


@dataclass
class OCRTextBlock:
    """A recognized text block with its bounding box."""
    text: str
    bbox: Tuple[float, float, float, float]  # normalized Vision coords (0-1, bottom-left origin)
    confidence: float


def extract_text_from_image(image_path: str, max_chars: int = 2000) -> str:
    """Extract text from image using macOS Vision framework.
    
    Args:
        image_path: Path to image file
        max_chars: Maximum characters to return (truncate if longer)
        
    Returns:
        Extracted text, truncated if necessary
        
    Raises:
        OCRError: If text extraction fails
    """
    if not VISION_AVAILABLE:
        raise OCRError("Vision framework not available - macOS 13+ required")
    
    image_path = pathlib.Path(image_path)
    if not image_path.exists():
        raise OCRError(f"Image file not found: {image_path}")
    
    handler = None
    request = None
    cg_image = None
    image_source = None

    try:
        # Load image
        image_url = NSURL.fileURLWithPath_(str(image_path))

        # Create CGImage from file
        image_source = Quartz.CGImageSourceCreateWithURL(image_url, None)
        if not image_source:
            raise OCRError("Failed to create image source")

        cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
        if not cg_image:
            raise OCRError("Failed to create CGImage")

        # Create Vision request
        request = Vision.VNRecognizeTextRequest.new()

        # Configure for better accuracy vs speed
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        # Create request handler and perform OCR
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})

        success = handler.performRequests_error_([request], None)
        if not success[0]:
            raise OCRError("Vision text recognition failed")

        # Extract text from results
        text_lines = []
        results = request.results()

        if results:
            for result in results:
                if hasattr(result, 'text'):
                    text_lines.append(result.text())

        # Join all text and truncate if necessary
        full_text = '\n'.join(text_lines)

        if len(full_text) > max_chars:
            truncated_text = full_text[:max_chars] + "..."
            logger.debug(f"OCR text truncated from {len(full_text)} to {max_chars} chars")
            return truncated_text

        logger.debug(f"OCR extracted {len(full_text)} characters")
        return full_text

    except OCRError:
        raise
    except Exception as e:
        raise OCRError(f"Text extraction failed: {e}") from e
    finally:
        # Explicit cleanup to help GC in long-running daemon
        del handler, request, cg_image, image_source


def extract_text_blocks(image_path: str, max_blocks: int = 200) -> Tuple[List[OCRTextBlock], int, int]:
    """Extract text blocks with bounding boxes from an image.

    Uses the same Vision pipeline as extract_text_from_image but preserves
    the spatial location (boundingBox) and confidence for each observation.

    Args:
        image_path: Path to image file.
        max_blocks: Maximum number of text blocks to return.

    Returns:
        Tuple of (blocks, image_width_px, image_height_px).

    Raises:
        OCRError: If text extraction fails.
    """
    if not VISION_AVAILABLE:
        raise OCRError("Vision framework not available - macOS 13+ required")

    image_path = pathlib.Path(image_path)
    if not image_path.exists():
        raise OCRError(f"Image file not found: {image_path}")

    handler = None
    request = None
    cg_image = None
    image_source = None

    try:
        image_url = NSURL.fileURLWithPath_(str(image_path))

        image_source = Quartz.CGImageSourceCreateWithURL(image_url, None)
        if not image_source:
            raise OCRError("Failed to create image source")

        cg_image = Quartz.CGImageSourceCreateImageAtIndex(image_source, 0, None)
        if not cg_image:
            raise OCRError("Failed to create CGImage")

        image_width = Quartz.CGImageGetWidth(cg_image)
        image_height = Quartz.CGImageGetHeight(cg_image)

        request = Vision.VNRecognizeTextRequest.new()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)

        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, {})
        success = handler.performRequests_error_([request], None)
        if not success[0]:
            raise OCRError("Vision text recognition failed")

        blocks: List[OCRTextBlock] = []
        results = request.results()

        if results:
            for result in results:
                if not hasattr(result, "text"):
                    continue

                text = result.text()
                if not text:
                    continue

                # boundingBox is a CGRect in normalized Vision coordinates
                # (origin bottom-left, values 0-1)
                bb = result.boundingBox()
                bbox = (
                    float(bb.origin.x),
                    float(bb.origin.y),
                    float(bb.size.width),
                    float(bb.size.height),
                )
                confidence = float(result.confidence())

                blocks.append(OCRTextBlock(text=text, bbox=bbox, confidence=confidence))

                if len(blocks) >= max_blocks:
                    break

        logger.debug(f"OCR extracted {len(blocks)} text blocks from {image_width}x{image_height} image")
        return blocks, image_width, image_height

    except OCRError:
        raise
    except Exception as e:
        raise OCRError(f"Text block extraction failed: {e}") from e
    finally:
        del handler, request, cg_image, image_source


def extract_text_from_screenshot(screenshot_path: str, max_chars: int = 2000) -> str:
    """Extract text from a screenshot file.
    
    This is a convenience wrapper around extract_text_from_image specifically
    for screenshot files captured by Coachy.
    
    Args:
        screenshot_path: Path to screenshot file
        max_chars: Maximum characters to return
        
    Returns:
        Extracted text or empty string if extraction fails
    """
    try:
        return extract_text_from_image(screenshot_path, max_chars)
    except OCRError as e:
        logger.warning(f"OCR failed for {screenshot_path}: {e}")
        return ""


def get_ocr_capabilities() -> dict:
    """Get information about OCR capabilities on this system.
    
    Returns:
        Dictionary with OCR capability information
    """
    capabilities = {
        "vision_available": VISION_AVAILABLE,
        "framework": None,
        "supported_languages": [],
        "recognition_levels": [],
    }
    
    if VISION_AVAILABLE:
        try:
            capabilities["framework"] = "Apple Vision"
            
            # Get supported recognition levels
            capabilities["recognition_levels"] = [
                "fast",     # VNRequestTextRecognitionLevelFast
                "accurate"  # VNRequestTextRecognitionLevelAccurate
            ]
            
            # Get supported languages (Vision supports many languages automatically)
            capabilities["supported_languages"] = [
                "en",  # English (primary)
                "auto"  # Automatic language detection
            ]
            
        except Exception as e:
            logger.warning(f"Failed to get Vision capabilities: {e}")
            capabilities["error"] = str(e)
    
    return capabilities


# Fallback OCR using pytesseract if Vision is not available
def _extract_text_tesseract(image_path: str, max_chars: int = 2000) -> str:
    """Fallback text extraction using tesseract OCR.
    
    Args:
        image_path: Path to image file
        max_chars: Maximum characters to return
        
    Returns:
        Extracted text
        
    Raises:
        OCRError: If tesseract is not available or fails
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise OCRError("Neither Vision nor pytesseract is available")
    
    try:
        # Open image with PIL
        with Image.open(image_path) as img:
            # Extract text using tesseract
            text = pytesseract.image_to_string(img, lang='eng')
            
            # Truncate if necessary
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            logger.debug(f"Tesseract OCR extracted {len(text)} characters")
            return text
            
    except Exception as e:
        raise OCRError(f"Tesseract OCR failed: {e}") from e


def test_ocr_functionality() -> bool:
    """Test OCR functionality with a simple test.
    
    Returns:
        True if OCR is working, False otherwise
    """
    capabilities = get_ocr_capabilities()
    
    if capabilities["vision_available"]:
        logger.info("Vision framework OCR available")
        return True
    
    # Try tesseract fallback
    try:
        import pytesseract
        logger.info("Tesseract OCR available as fallback")
        return True
    except ImportError:
        logger.warning("No OCR backend available (Vision or tesseract)")
        return False


if __name__ == "__main__":
    # Simple test of OCR capabilities
    print("OCR Capabilities Test")
    print("=" * 30)
    
    capabilities = get_ocr_capabilities()
    for key, value in capabilities.items():
        print(f"{key}: {value}")
    
    working = test_ocr_functionality()
    print(f"\nOCR working: {working}")