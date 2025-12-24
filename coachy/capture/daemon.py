"""Background capture daemon for Coachy."""
import logging
import os
import pathlib
import signal
import sys
import time
from multiprocessing import Process

from ..config import get_config
from ..storage.db import get_database
from ..storage.models import ActivityEntry
from ..process.pipeline import create_processor
from .screenshot import capture_screenshot, ScreenshotError
from .window import get_active_window, is_screen_locked

logger = logging.getLogger(__name__)


class CaptureMode:
    """Operating modes for capture daemon."""
    NORMAL = "normal"      # Normal capture with screenshots
    EXCLUDED = "excluded"  # App is excluded, no screenshot but log activity
    LOCKED = "locked"      # Screen is locked, pause capture


class CaptureDaemon:
    """Background daemon for capturing screenshots and activity."""
    
    def __init__(self):
        """Initialize capture daemon."""
        self.config = get_config()
        self.db = get_database(self.config.db_path)
        self.processor = create_processor()
        self.running = False
        self.pid_file = pathlib.Path("data/coachy.pid")
        
        # Set up logging
        self._setup_logging()
        
        # Create screenshots directory
        screenshots_dir = pathlib.Path(self.config.screenshots_path)
        screenshots_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_logging(self) -> None:
        """Configure logging for the daemon."""
        log_file = pathlib.Path(self.config.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Configure root logger
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()  # Also log to console
            ]
        )
    
    def _write_pid_file(self) -> None:
        """Write process ID to file."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"PID file written: {self.pid_file}")
    
    def _remove_pid_file(self) -> None:
        """Remove PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()
            logger.info("PID file removed")
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
    
    def _determine_capture_mode(self, window_info) -> CaptureMode:
        """Determine capture mode based on current state.
        
        Args:
            window_info: Current window information
            
        Returns:
            Capture mode to use
        """
        # Check if screen is locked
        if is_screen_locked():
            return CaptureMode.LOCKED
        
        # Check if current app/window is excluded
        if window_info.is_excluded(
            self.config.excluded_apps,
            self.config.excluded_titles
        ):
            return CaptureMode.EXCLUDED
        
        return CaptureMode.NORMAL
    
    def _capture_cycle(self) -> None:
        """Perform one capture cycle."""
        try:
            # Get current window information
            window_info = get_active_window()
            
            # Determine capture mode
            mode = self._determine_capture_mode(window_info)
            
            if mode == CaptureMode.LOCKED:
                logger.debug("Screen locked, skipping capture")
                time.sleep(self.config.capture_interval)
                return
            
            screenshot_path = None
            
            if mode == CaptureMode.EXCLUDED:
                # Log excluded activity without screenshot
                logger.debug(f"Excluded app: {window_info.app_name}")
                # Process through pipeline but mark as excluded
                activity = self.processor.process_activity(
                    app_name=window_info.app_name,
                    window_title=window_info.window_title,
                    screenshot_path=None,
                    duration_seconds=self.config.capture_interval
                )
                activity.metadata = activity.metadata or {}
                activity.metadata.update({"excluded": True, "reason": "app_excluded"})
                
            elif mode == CaptureMode.NORMAL:
                # Normal capture with screenshot
                try:
                    # Generate screenshot filename
                    timestamp = int(time.time() * 1000)
                    screenshot_name = f"screenshot_{timestamp}.jpg"
                    screenshot_path = pathlib.Path(self.config.screenshots_path) / screenshot_name
                    
                    # Capture screenshot
                    saved_path = capture_screenshot(
                        monitor=self.config.capture_monitors,
                        output_path=str(screenshot_path),
                        quality=85
                    )
                    
                    screenshot_path = saved_path
                    logger.debug(f"Screenshot captured: {saved_path}")
                    
                except ScreenshotError as e:
                    logger.error(f"Screenshot capture failed: {e}")
                    screenshot_path = None
                
                # Process through full pipeline (OCR + classification)
                activity = self.processor.process_activity(
                    app_name=window_info.app_name,
                    window_title=window_info.window_title,
                    screenshot_path=screenshot_path,
                    duration_seconds=self.config.capture_interval
                )
                
                # Add screenshot error to metadata if capture failed
                if screenshot_path is None:
                    activity.metadata = activity.metadata or {}
                    activity.metadata.update({"screenshot_error": "Screenshot capture failed"})
            
            # Store processed activity in database
            activity_id = self.db.insert_activity(activity)
            logger.debug(
                f"Activity logged: ID {activity_id}, app: {window_info.app_name}, "
                f"category: {activity.category}, ocr_chars: {len(activity.ocr_text or '')}"
            )
            
        except Exception as e:
            logger.error(f"Capture cycle failed: {e}")
    
    def run(self) -> None:
        """Run the capture daemon."""
        if not self.config.capture_enabled:
            logger.error("Capture is disabled in configuration")
            return
        
        logger.info("Starting Coachy capture daemon...")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Write PID file
        self._write_pid_file()
        
        self.running = True
        
        try:
            logger.info(f"Capture started - interval: {self.config.capture_interval}s")
            
            while self.running:
                cycle_start = time.time()
                
                # Perform capture cycle
                self._capture_cycle()
                
                # Sleep for remaining interval time
                cycle_duration = time.time() - cycle_start
                sleep_time = max(0, self.config.capture_interval - cycle_duration)
                
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    logger.warning(
                        f"Capture cycle took {cycle_duration:.1f}s, "
                        f"longer than interval {self.config.capture_interval}s"
                    )
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        
        except Exception as e:
            logger.error(f"Daemon crashed: {e}")
            raise
        
        finally:
            self.running = False
            self._remove_pid_file()
            self.db.close()
            logger.info("Coachy capture daemon stopped")


def start_daemon() -> None:
    """Start the capture daemon as a background process."""
    pid_file = pathlib.Path("data/coachy.pid")
    
    # Check if daemon is already running
    if pid_file.exists():
        try:
            with open(pid_file, 'r') as f:
                existing_pid = int(f.read().strip())
            
            # Check if process is actually running
            try:
                os.kill(existing_pid, 0)  # Signal 0 just checks if process exists
                raise RuntimeError(f"Daemon already running with PID {existing_pid}")
            except OSError:
                # Process doesn't exist, remove stale PID file
                pid_file.unlink()
                logger.warning(f"Removed stale PID file: {pid_file}")
        except (ValueError, FileNotFoundError):
            # Invalid PID file, remove it
            pid_file.unlink()
    
    # Start daemon process
    daemon = CaptureDaemon()
    
    def run_daemon():
        """Target function for daemon process."""
        daemon.run()
    
    # Start as separate process
    process = Process(target=run_daemon)
    process.start()
    
    # Wait a moment to see if process started successfully
    time.sleep(1)
    if process.is_alive():
        logger.info(f"Capture daemon started with PID {process.pid}")
    else:
        raise RuntimeError("Failed to start daemon process")


def stop_daemon() -> None:
    """Stop the capture daemon."""
    pid_file = pathlib.Path("data/coachy.pid")
    
    if not pid_file.exists():
        raise RuntimeError("Daemon not running (no PID file found)")
    
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        # Send SIGTERM to gracefully stop the daemon
        os.kill(pid, signal.SIGTERM)
        
        # Wait for process to stop
        for _ in range(10):  # Wait up to 10 seconds
            try:
                os.kill(pid, 0)  # Check if process still exists
                time.sleep(1)
            except OSError:
                # Process no longer exists
                break
        else:
            # Process didn't stop gracefully, force kill
            logger.warning("Daemon didn't stop gracefully, force killing...")
            os.kill(pid, signal.SIGKILL)
        
        # Remove PID file if it still exists
        if pid_file.exists():
            pid_file.unlink()
        
        logger.info(f"Capture daemon stopped (PID {pid})")
        
    except (ValueError, FileNotFoundError, OSError) as e:
        raise RuntimeError(f"Failed to stop daemon: {e}")


def get_daemon_status() -> dict:
    """Get status of the capture daemon.
    
    Returns:
        Dictionary with daemon status information
    """
    pid_file = pathlib.Path("data/coachy.pid")
    
    if not pid_file.exists():
        return {"running": False, "pid": None}
    
    try:
        with open(pid_file, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if process is actually running
        try:
            os.kill(pid, 0)
            return {"running": True, "pid": pid}
        except OSError:
            # Process doesn't exist, remove stale PID file
            pid_file.unlink()
            return {"running": False, "pid": None, "stale_pid_removed": True}
            
    except (ValueError, FileNotFoundError):
        return {"running": False, "pid": None, "invalid_pid_file": True}