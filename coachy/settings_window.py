"""Native macOS settings window using PyObjC.

Provides a simple NSWindow with controls for:
  - API key (stored in Keychain)
  - Privacy level & default coach
  - Capture interval
  - Data management (cleanup, open folder)
  - Auto-start on login
"""
import logging
import pathlib
import sys

import yaml

try:
    import objc
    from AppKit import (
        NSApp,
        NSBackingStoreBuffered,
        NSButton,
        NSBezelStyleRounded,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSEvent,
        NSFont,
        NSMakeRect,
        NSObject,
        NSPopUpButton,
        NSScreen,
        NSSecureTextField,
        NSTextField,
        NSWindow,
        NSWindowStyleMaskTitled,
        NSWindowStyleMaskClosable,
        NSWorkspace,
    )
    _APPKIT_AVAILABLE = True
except ImportError:
    _APPKIT_AVAILABLE = False

from .app_paths import get_app_dir, get_config_path, get_personas_dir
from .config import get_config, reset_config
from .keychain import set_api_key, has_api_key
from .storage.db import get_database

logger = logging.getLogger(__name__)

WINDOW_WIDTH = 480
WINDOW_HEIGHT = 520
PADDING = 20
ROW_HEIGHT = 28
LABEL_WIDTH = 130
FIELD_WIDTH = WINDOW_WIDTH - LABEL_WIDTH - PADDING * 3


# ObjC helper: forwards NSButton actions to Python callables.
if _APPKIT_AVAILABLE:
    class _ButtonTarget(NSObject):
        def initWithCallback_(self, callback):
            self = objc.super(_ButtonTarget, self).init()
            if self is None:
                return None
            self._callback = callback
            return self

        def performAction_(self, sender):
            if self._callback:
                try:
                    self._callback()
                except Exception as exc:
                    logger.error(f"Button callback error: {exc}", exc_info=True)


class SettingsWindowController:
    """Controls the settings NSWindow."""

    def __init__(self):
        if not _APPKIT_AVAILABLE:
            raise RuntimeError("AppKit not available — settings window requires macOS")

        self._window = None
        self._fields = {}       # name -> control
        self._button_targets = []  # prevent GC of ObjC targets

    def show(self):
        """Show the settings window, creating it if needed."""
        if self._window is None:
            self._build_window()
        self._position_below_menubar()
        self._populate_fields()
        self._window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _position_below_menubar(self):
        """Position the window just below the menu bar item that was clicked."""
        mouse = NSEvent.mouseLocation()  # screen coords, origin bottom-left
        screen = NSScreen.mainScreen().frame()

        # Center horizontally on mouse X, clamp to screen edges
        x = mouse.x - WINDOW_WIDTH / 2
        x = max(screen.origin.x, min(x, screen.origin.x + screen.size.width - WINDOW_WIDTH))

        # Place top edge of window just below the menu bar (~24pt)
        menu_bar_height = 24
        y = screen.origin.y + screen.size.height - menu_bar_height - WINDOW_HEIGHT

        self._window.setFrameOrigin_((x, y))

    # ---- window construction ----

    def _build_window(self):
        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 200, WINDOW_WIDTH, WINDOW_HEIGHT),
            style,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("Coachy Settings")
        self._window.setReleasedWhenClosed_(False)

        content = self._window.contentView()
        y = WINDOW_HEIGHT - PADDING - ROW_HEIGHT  # top-down layout

        # -- API Key --
        y = self._add_section_header(content, "API Key", y)
        y = self._add_secure_field(content, "api_key", "Anthropic Key:", y)
        y = self._add_button(content, "Save Key", self._save_api_key, y)
        self._fields["api_key_status"] = self._add_label(
            content, "", y + ROW_HEIGHT + 4, italic=True
        )
        y -= 8

        # -- Privacy & Coach --
        y = self._add_section_header(content, "Privacy & Coach", y)
        y = self._add_popup(content, "privacy_level", "Privacy:", ["private", "detailed"], y)
        try:
            from .coach.personas import get_persona_manager
            personas = get_persona_manager().list_personas()
        except Exception:
            personas = ["grove"]
        y = self._add_popup(content, "default_persona", "Default Coach:", personas, y)
        y = self._add_button(content, "Open Personas Folder", self._open_personas_folder, y)
        y -= 8

        # -- Capture --
        y = self._add_section_header(content, "Capture", y)
        y = self._add_text_field(content, "interval", "Interval (sec):", y, placeholder="60")
        y = self._add_checkbox(content, "auto_start", "Start Coachy on login", y)
        y -= 8

        # -- Data Management --
        y = self._add_section_header(content, "Data Management", y)
        self._fields["data_info"] = self._add_label(content, "", y)
        y -= ROW_HEIGHT
        y = self._add_button(content, "Clean Up Old Data", self._run_cleanup, y)
        y = self._add_button(content, "Open Data Folder", self._open_data_folder, y)
        y -= 8

        # -- Save --
        y = self._add_button(content, "Save Settings", self._save_settings, y, width=120)

    # ---- widget helpers ----

    def _add_section_header(self, parent, text, y):
        label = NSTextField.labelWithString_(text)
        label.setFont_(NSFont.boldSystemFontOfSize_(13))
        label.setFrame_(NSMakeRect(PADDING, y, WINDOW_WIDTH - PADDING * 2, ROW_HEIGHT))
        parent.addSubview_(label)
        return y - ROW_HEIGHT

    def _add_label(self, parent, text, y, italic=False):
        label = NSTextField.labelWithString_(text)
        if italic:
            label.setFont_(NSFont.systemFontOfSize_weight_(11, 0.0))
        label.setFrame_(NSMakeRect(PADDING + LABEL_WIDTH, y, FIELD_WIDTH, ROW_HEIGHT))
        parent.addSubview_(label)
        return label

    def _add_secure_field(self, parent, name, label_text, y):
        lbl = NSTextField.labelWithString_(label_text)
        lbl.setFrame_(NSMakeRect(PADDING, y, LABEL_WIDTH, ROW_HEIGHT))
        parent.addSubview_(lbl)
        field = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING + LABEL_WIDTH, y, FIELD_WIDTH, ROW_HEIGHT)
        )
        field.setPlaceholderString_("sk-ant-...")
        parent.addSubview_(field)
        self._fields[name] = field
        return y - ROW_HEIGHT - 4

    def _add_text_field(self, parent, name, label_text, y, placeholder=""):
        lbl = NSTextField.labelWithString_(label_text)
        lbl.setFrame_(NSMakeRect(PADDING, y, LABEL_WIDTH, ROW_HEIGHT))
        parent.addSubview_(lbl)
        field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING + LABEL_WIDTH, y, 80, ROW_HEIGHT)
        )
        field.setPlaceholderString_(placeholder)
        parent.addSubview_(field)
        self._fields[name] = field
        return y - ROW_HEIGHT - 4

    def _add_popup(self, parent, name, label_text, items, y):
        lbl = NSTextField.labelWithString_(label_text)
        lbl.setFrame_(NSMakeRect(PADDING, y, LABEL_WIDTH, ROW_HEIGHT))
        parent.addSubview_(lbl)
        popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(PADDING + LABEL_WIDTH, y, 160, ROW_HEIGHT), False
        )
        for item in items:
            popup.addItemWithTitle_(item)
        parent.addSubview_(popup)
        self._fields[name] = popup
        return y - ROW_HEIGHT - 4

    def _add_checkbox(self, parent, name, label_text, y):
        btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(PADDING + LABEL_WIDTH, y, FIELD_WIDTH, ROW_HEIGHT)
        )
        btn.setButtonType_(3)  # NSSwitchButton
        btn.setTitle_(label_text)
        parent.addSubview_(btn)
        self._fields[name] = btn
        return y - ROW_HEIGHT - 4

    def _add_button(self, parent, title, action, y, width=None):
        btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(PADDING + LABEL_WIDTH, y, width or 180, ROW_HEIGHT)
        )
        btn.setTitle_(title)
        btn.setBezelStyle_(NSBezelStyleRounded)
        target = _ButtonTarget.alloc().initWithCallback_(action)
        btn.setTarget_(target)
        btn.setAction_(b"performAction:")
        self._button_targets.append(target)
        parent.addSubview_(btn)
        return y - ROW_HEIGHT - 4

    # ---- populate ----

    def _populate_fields(self):
        """Fill controls with current values."""
        if has_api_key():
            self._fields["api_key_status"].setStringValue_("Saved in Keychain")
        else:
            self._fields["api_key_status"].setStringValue_("Not set")

        try:
            reset_config()  # re-read from disk in case file changed
            config = get_config()
        except Exception:
            # Config missing or invalid — use defaults so fields aren't blank
            self._fields["interval"].setStringValue_("60")
            return

        # Privacy
        popup = self._fields["privacy_level"]
        idx = popup.indexOfItemWithTitle_(config.privacy_level)
        if idx >= 0:
            popup.selectItemAtIndex_(idx)

        # Persona
        persona = config.get("coach.default_persona", "grove")
        popup = self._fields["default_persona"]
        idx = popup.indexOfItemWithTitle_(persona)
        if idx >= 0:
            popup.selectItemAtIndex_(idx)

        # Interval
        self._fields["interval"].setStringValue_(str(config.capture_interval))

        # Auto-start
        state = (
            NSControlStateValueOn if self._launchagent_path().exists()
            else NSControlStateValueOff
        )
        self._fields["auto_start"].setState_(state)

        # Data info
        self._update_data_info()

    def _update_data_info(self):
        try:
            config = get_config()
            db = get_database(config.db_path)
            stats = db.get_database_stats()
            db_mb = stats["file_size_bytes"] / 1024 / 1024
            screenshots_dir = pathlib.Path(config.screenshots_path)
            sc_count = (
                len(list(screenshots_dir.glob("*.jpg")))
                if screenshots_dir.exists() else 0
            )
            self._fields["data_info"].setStringValue_(
                f"DB: {db_mb:.1f} MB  |  Screenshots: {sc_count}"
            )
        except Exception:
            self._fields["data_info"].setStringValue_("(no data yet)")

    # ---- actions ----

    def _save_api_key(self):
        key = self._fields["api_key"].stringValue()
        if key:
            set_api_key(key)
            self._fields["api_key_status"].setStringValue_("Saved in Keychain")
            self._fields["api_key"].setStringValue_("")

    def _save_settings(self):
        """Merge changed settings into config.yaml, preserving all other fields."""
        import rumps
        config_path = get_config_path()

        # Read the full existing config so we don't lose anything
        data = None
        try:
            with open(config_path, "r") as f:
                raw = f.read()
            data = yaml.safe_load(raw)
        except (FileNotFoundError, yaml.YAMLError):
            pass

        # If config is missing/empty/corrupt, seed from the example file
        if not isinstance(data, dict) or len(data) < 4:
            try:
                from .app_paths import get_bundle_resources_dir
                example_path = get_bundle_resources_dir() / "config.yaml.example"
                with open(example_path, "r") as f:
                    data = yaml.safe_load(f.read())
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}

        # Update only the fields we manage
        if "coach" not in data:
            data["coach"] = {}
        data["coach"]["privacy_level"] = str(
            self._fields["privacy_level"].titleOfSelectedItem()
        )
        data["coach"]["default_persona"] = str(
            self._fields["default_persona"].titleOfSelectedItem()
        )

        try:
            interval = int(str(self._fields["interval"].stringValue()))
            interval = max(10, min(300, interval))
        except (ValueError, TypeError):
            interval = 60
        if "capture" not in data:
            data["capture"] = {}
        data["capture"]["interval_seconds"] = interval

        # Write config
        try:
            with open(config_path, "w") as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        except Exception as exc:
            logger.error(f"Failed to write config: {exc}")
            rumps.notification("Coachy", "Settings error", f"Could not save: {exc}")
            return

        # Reload config singleton (non-fatal if it fails)
        try:
            reset_config()
        except Exception as exc:
            logger.warning(f"Config reload after save: {exc}")

        # Launch agent toggle (non-fatal)
        try:
            if self._fields["auto_start"].state() == NSControlStateValueOn:
                self._install_launchagent()
            else:
                self._remove_launchagent()
        except Exception as exc:
            logger.warning(f"Launch agent update: {exc}")

        logger.info("Settings saved")

        # Always close the window
        self._window.performClose_(None)

    def _open_personas_folder(self):
        NSWorkspace.sharedWorkspace().openFile_(str(get_personas_dir()))

    def _open_data_folder(self):
        NSWorkspace.sharedWorkspace().openFile_(str(get_app_dir() / "data"))

    def _run_cleanup(self):
        try:
            from datetime import datetime
            config = get_config()
            db = get_database(config.db_path)
            cutoff = int(datetime.now().timestamp()) - config.retention_days * 86400
            db.cleanup_old_activities(cutoff)
            self._update_data_info()
        except Exception as exc:
            logger.error(f"Cleanup failed: {exc}")

    # ---- launch agent ----

    def _launchagent_path(self) -> pathlib.Path:
        return pathlib.Path.home() / "Library" / "LaunchAgents" / "com.coachy.agent.plist"

    def _install_launchagent(self):
        """Write a launchd plist to auto-start Coachy on login."""
        plist_path = self._launchagent_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        if getattr(sys, "frozen", False):
            app_path = pathlib.Path(sys.executable).parent.parent.parent
            args_xml = f"        <string>{app_path / 'Contents' / 'MacOS' / 'Coachy'}</string>"
        else:
            args_xml = (
                f"        <string>{sys.executable}</string>\n"
                f"        <string>-m</string>\n"
                f"        <string>coachy.menubar</string>"
            )

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.coachy.agent</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
        plist_path.write_text(plist_content)
        logger.info(f"Installed launch agent: {plist_path}")

    def _remove_launchagent(self):
        plist_path = self._launchagent_path()
        if plist_path.exists():
            plist_path.unlink()
            logger.info("Removed launch agent")
