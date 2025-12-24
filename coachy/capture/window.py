"""Active window detection using macOS AppKit framework."""
import logging
from dataclasses import dataclass
from typing import Optional

try:
    import AppKit
    from AppKit import NSWorkspace
    APPKIT_AVAILABLE = True
except ImportError:
    APPKIT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    """Information about the active window."""
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    bundle_id: Optional[str] = None
    process_id: Optional[int] = None
    
    def is_excluded(self, excluded_apps: list, excluded_titles: list) -> bool:
        """Check if this window should be excluded from capture.
        
        Args:
            excluded_apps: List of app names to exclude (case-insensitive substring match)
            excluded_titles: List of window titles to exclude (case-insensitive substring match)
            
        Returns:
            True if window should be excluded
        """
        # Check app name exclusions
        if self.app_name:
            app_name_lower = self.app_name.lower()
            for excluded_app in excluded_apps:
                if excluded_app.lower() in app_name_lower:
                    return True
        
        # Check window title exclusions
        if self.window_title:
            window_title_lower = self.window_title.lower()
            for excluded_title in excluded_titles:
                if excluded_title.lower() in window_title_lower:
                    return True
        
        return False


def get_active_window() -> WindowInfo:
    """Get information about the currently active window.
    
    Returns:
        WindowInfo object with active window details
    """
    if not APPKIT_AVAILABLE:
        logger.warning("AppKit framework not available - limited window detection")
        return WindowInfo()
    
    try:
        # Get the active application
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        
        if active_app is None:
            logger.warning("No active application found")
            return WindowInfo()
        
        # Get basic app info
        app_name = active_app.localizedName()
        bundle_id = active_app.bundleIdentifier()
        process_id = active_app.processIdentifier()
        
        # Get window title using AppleScript (more reliable than NSWindow APIs)
        window_title = _get_window_title_applescript(app_name)
        
        return WindowInfo(
            app_name=app_name,
            window_title=window_title,
            bundle_id=bundle_id,
            process_id=process_id
        )
        
    except Exception as e:
        logger.error(f"Failed to get active window info: {e}")
        return WindowInfo()


def _get_window_title_applescript(app_name: str) -> Optional[str]:
    """Get window title using AppleScript for better compatibility.
    
    Args:
        app_name: Name of the application
        
    Returns:
        Window title or None if not available
    """
    try:
        import subprocess
        
        # AppleScript to get the front window title
        script = f'''
        tell application "System Events"
            try
                tell process "{app_name}"
                    set frontWindow to first window
                    return title of frontWindow
                end tell
            on error
                return ""
            end try
        end tell
        '''
        
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=2  # Short timeout to avoid hanging
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        
    except Exception as e:
        logger.debug(f"AppleScript window title detection failed: {e}")
    
    return None


def get_running_apps() -> list:
    """Get list of currently running applications.
    
    Returns:
        List of dictionaries with app information
    """
    if not APPKIT_AVAILABLE:
        return []
    
    try:
        workspace = NSWorkspace.sharedWorkspace()
        running_apps = workspace.runningApplications()
        
        apps = []
        for app in running_apps:
            # Skip background apps without UI
            if not app.activationPolicy() == AppKit.NSApplicationActivationPolicyRegular:
                continue
                
            app_info = {
                'name': app.localizedName(),
                'bundle_id': app.bundleIdentifier(),
                'process_id': app.processIdentifier(),
                'is_active': app.isActive(),
                'is_frontmost': app == workspace.frontmostApplication()
            }
            apps.append(app_info)
        
        return apps
        
    except Exception as e:
        logger.error(f"Failed to get running apps: {e}")
        return []


def is_screen_locked() -> bool:
    """Check if the screen is currently locked.
    
    Returns:
        True if screen is locked
    """
    try:
        import subprocess
        
        # Use pmset to check if display is sleeping
        result = subprocess.run(
            ['pmset', '-g', 'powerstate', 'IODisplayWrangler'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            # If display wrangler is in state 0, screen is off/locked
            return '0' in result.stdout
            
    except Exception as e:
        logger.debug(f"Screen lock detection failed: {e}")
    
    # Default to not locked if we can't determine
    return False