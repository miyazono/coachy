"""Processing pipeline orchestration for screenshots and activities."""
import logging
import time
from typing import Optional, Dict, Any

from ..config import get_config
from ..storage.models import ActivityEntry
from .ocr import extract_text_from_screenshot, OCRError
from .classifier import ActivityClassifier, ClassifierError

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Exception raised when processing pipeline fails."""
    pass


class ActivityProcessor:
    """Orchestrates OCR and classification of captured activities."""
    
    def __init__(self):
        """Initialize the activity processor."""
        self.config = get_config()
        self.classifier = ActivityClassifier(
            backend=self.config.get('processing.classifier_backend', 'rules')
        )
        self.ocr_enabled = self.config.get('processing.ocr_enabled', True)
    
    def process_activity(
        self,
        app_name: Optional[str],
        window_title: Optional[str],
        screenshot_path: Optional[str],
        duration_seconds: int = 60
    ) -> ActivityEntry:
        """Process a captured activity through the full pipeline.
        
        Args:
            app_name: Name of the active application
            window_title: Title of the active window
            screenshot_path: Path to screenshot file (optional)
            duration_seconds: Duration to attribute to this activity
            
        Returns:
            Processed ActivityEntry ready for database storage
        """
        start_time = time.time()
        processing_metadata = {}
        
        try:
            # Step 1: Extract text from screenshot (if available and enabled)
            ocr_text = None
            if screenshot_path and self.ocr_enabled:
                ocr_text = self._extract_text(screenshot_path, processing_metadata)
            
            # Step 2: Classify the activity
            category = self._classify_activity(
                app_name, window_title, ocr_text, processing_metadata
            )
            
            # Step 3: Create activity entry with processed data
            activity = ActivityEntry.create_now(
                app_name=app_name,
                window_title=window_title,
                category=category,
                ocr_text=ocr_text,
                screenshot_path=screenshot_path,
                duration_seconds=duration_seconds,
                metadata={
                    "processing": processing_metadata,
                    "processing_time_ms": int((time.time() - start_time) * 1000)
                }
            )
            
            logger.debug(
                f"Processed activity: app={app_name}, category={category}, "
                f"ocr_chars={len(ocr_text) if ocr_text else 0}, "
                f"time={activity.metadata['processing_time_ms']}ms"
            )
            
            return activity
            
        except Exception as e:
            # Create activity entry even if processing fails
            logger.error(f"Processing failed: {e}")
            
            activity = ActivityEntry.create_now(
                app_name=app_name,
                window_title=window_title,
                category="unknown",
                screenshot_path=screenshot_path,
                duration_seconds=duration_seconds,
                metadata={
                    "processing": processing_metadata,
                    "processing_error": str(e),
                    "processing_time_ms": int((time.time() - start_time) * 1000)
                }
            )
            
            return activity
    
    def _extract_text(self, screenshot_path: str, metadata: Dict[str, Any]) -> Optional[str]:
        """Extract text from screenshot with error handling.
        
        Args:
            screenshot_path: Path to screenshot file
            metadata: Dictionary to store processing metadata
            
        Returns:
            Extracted text or None if extraction fails
        """
        ocr_start = time.time()
        
        try:
            max_chars = 2000  # Limit OCR text length
            ocr_text = extract_text_from_screenshot(screenshot_path, max_chars)
            
            ocr_time_ms = int((time.time() - ocr_start) * 1000)
            metadata.update({
                "ocr_success": True,
                "ocr_time_ms": ocr_time_ms,
                "ocr_chars": len(ocr_text) if ocr_text else 0,
                "ocr_backend": "vision"
            })
            
            if ocr_text:
                logger.debug(f"OCR extracted {len(ocr_text)} chars in {ocr_time_ms}ms")
            else:
                logger.debug(f"OCR found no text in {ocr_time_ms}ms")
            
            return ocr_text if ocr_text else None
            
        except OCRError as e:
            ocr_time_ms = int((time.time() - ocr_start) * 1000)
            metadata.update({
                "ocr_success": False,
                "ocr_error": str(e),
                "ocr_time_ms": ocr_time_ms
            })
            
            logger.warning(f"OCR failed for {screenshot_path}: {e}")
            return None
    
    def _classify_activity(
        self,
        app_name: Optional[str],
        window_title: Optional[str],
        ocr_text: Optional[str],
        metadata: Dict[str, Any]
    ) -> str:
        """Classify activity with error handling.
        
        Args:
            app_name: Name of the active application
            window_title: Title of the active window
            ocr_text: Extracted OCR text
            metadata: Dictionary to store processing metadata
            
        Returns:
            Activity category
        """
        classify_start = time.time()
        
        try:
            category = self.classifier.classify(app_name, window_title, ocr_text)
            
            classify_time_ms = int((time.time() - classify_start) * 1000)
            metadata.update({
                "classification_success": True,
                "classification_time_ms": classify_time_ms,
                "classifier_backend": self.classifier.backend,
                "category": category
            })
            
            logger.debug(f"Classified as '{category}' in {classify_time_ms}ms")
            return category
            
        except Exception as e:
            classify_time_ms = int((time.time() - classify_start) * 1000)
            metadata.update({
                "classification_success": False,
                "classification_error": str(e),
                "classification_time_ms": classify_time_ms
            })
            
            logger.warning(f"Classification failed: {e}")
            return "unknown"
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get statistics about processing performance.
        
        Returns:
            Dictionary with processing statistics
        """
        return {
            "ocr_enabled": self.ocr_enabled,
            "classifier_backend": self.classifier.backend,
            "available_categories": list(self.classifier.get_all_categories().keys())
        }


class BatchProcessor:
    """Processes multiple activities in batch for efficiency."""
    
    def __init__(self):
        """Initialize batch processor."""
        self.processor = ActivityProcessor()
    
    def process_unprocessed_activities(self, db) -> int:
        """Process activities that haven't been processed yet.
        
        Args:
            db: Database instance
            
        Returns:
            Number of activities processed
        """
        # This would be used for reprocessing old activities
        # when upgrading from Phase 1 to Phase 2
        logger.info("Batch processing not implemented in Phase 2")
        return 0
    
    def reprocess_activities_by_timerange(self, db, start_timestamp: int, end_timestamp: int) -> int:
        """Reprocess activities in a specific time range.
        
        Args:
            db: Database instance
            start_timestamp: Start time (Unix timestamp)
            end_timestamp: End time (Unix timestamp)
            
        Returns:
            Number of activities reprocessed
        """
        logger.info("Activity reprocessing not implemented in Phase 2")
        return 0


def create_processor() -> ActivityProcessor:
    """Create and return a configured activity processor.
    
    Returns:
        ActivityProcessor instance
    """
    return ActivityProcessor()


def test_processing_pipeline():
    """Test the processing pipeline with mock data."""
    print("Testing Processing Pipeline")
    print("=" * 40)
    
    processor = ActivityProcessor()
    
    # Test cases with different scenarios
    test_cases = [
        {
            "app_name": "VS Code",
            "window_title": "main.py - myproject",
            "screenshot_path": None,  # No screenshot
            "expected_category": "deep_work"
        },
        {
            "app_name": "Chrome",
            "window_title": "GitHub - microsoft/vscode",
            "screenshot_path": None,
            "expected_category": "research"
        },
        {
            "app_name": "Slack",
            "window_title": "general | MyCompany",
            "screenshot_path": None,
            "expected_category": "communication"
        },
        {
            "app_name": "Unknown App",
            "window_title": "Some Window",
            "screenshot_path": None,
            "expected_category": "unknown"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['app_name']}")
        
        try:
            activity = processor.process_activity(
                app_name=test_case["app_name"],
                window_title=test_case["window_title"],
                screenshot_path=test_case["screenshot_path"]
            )
            
            result = "✓" if activity.category == test_case["expected_category"] else "✗"
            print(f"  {result} Expected: {test_case['expected_category']}, Got: {activity.category}")
            
            if activity.metadata and "processing_time_ms" in activity.metadata:
                print(f"  Processing time: {activity.metadata['processing_time_ms']}ms")
                
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    # Test processor stats
    stats = processor.get_processing_stats()
    print(f"\nProcessor Configuration:")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    test_processing_pipeline()