"""Coachy menu bar application.

Entry point for the macOS menu bar app. Uses ``rumps`` for the status-bar icon
and menu, and ``DaemonThread`` for in-process screen capture.
"""
import logging
import threading
from datetime import datetime

import rumps

from .app_paths import get_config_path, get_app_dir
from .capture.daemon_thread import DaemonThread
from .config import get_config, reset_config
from .errors import friendly_error
from .storage.db import get_database

logger = logging.getLogger(__name__)

# How often (seconds) the status timer fires
STATUS_POLL_INTERVAL = 10


class CoachyApp(rumps.App):
    """Menu bar application for Coachy."""

    def __init__(self):
        super().__init__(
            name="Coachy",
            title="C",
            quit_button=None,  # we supply our own so we can clean up
        )

        # Daemon
        self._daemon = DaemonThread(on_error=self._on_daemon_error)

        # Build menu
        self._toggle_item = rumps.MenuItem("Start Capture", callback=self._toggle_capture)
        self._digest_menu = rumps.MenuItem("Generate Digest")
        self._digest_menu.add(rumps.MenuItem("Daily Digest", callback=self._daily_digest))
        self._digest_menu.add(rumps.MenuItem("Weekly Digest", callback=self._weekly_digest))
        self._digest_menu.add(rumps.separator)
        self._coach_label = rumps.MenuItem("Coach: grove")
        self._coach_label.set_callback(None)
        self._digest_menu.add(self._coach_label)

        self._status_item = rumps.MenuItem("Status: Stopped")
        self._status_item.set_callback(None)

        self._settings_item = rumps.MenuItem("Settings...", callback=self._open_settings)
        self._quit_item = rumps.MenuItem("Quit Coachy", callback=self._quit)

        self.menu = [
            self._toggle_item,
            rumps.separator,
            self._digest_menu,
            rumps.separator,
            self._status_item,
            rumps.separator,
            self._settings_item,
            rumps.separator,
            self._quit_item,
        ]

        # Status polling timer
        self._timer = rumps.Timer(self._poll_status, STATUS_POLL_INTERVAL)
        self._timer.start()

        # Settings window controller (lazy)
        self._settings_controller = None

    # ---- first-run ----

    def _first_run_setup(self):
        """Copy defaults and open settings if this is a fresh install."""
        import shutil
        from .app_paths import get_bundle_resources_dir, get_personas_dir

        resources = get_bundle_resources_dir()

        # Copy config.yaml.example → config.yaml
        config_path = get_config_path()
        if not config_path.exists():
            src = resources / "config.yaml.example"
            if src.exists():
                config_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(config_path))

        # Copy persona files
        personas_src = resources / "personas"
        personas_dst = get_personas_dir()
        if personas_src.exists():
            for md in personas_src.glob("*.md"):
                dst = personas_dst / md.name
                if not dst.exists():
                    shutil.copy2(str(md), str(dst))

        # Copy priorities.md.example
        from .app_paths import get_priorities_path
        priorities_path = get_priorities_path()
        if not priorities_path.exists():
            src = resources / "priorities.md.example"
            if src.exists():
                shutil.copy2(str(src), str(priorities_path))

        # Show welcome
        rumps.notification(
            title="Welcome to Coachy",
            subtitle="",
            message="Add your Anthropic API key in Settings to get started.",
        )

        # Auto-open settings
        self._open_settings(None)

    # ---- callbacks ----

    def _toggle_capture(self, sender):
        try:
            if self._daemon.is_running():
                self._daemon.stop()
                sender.title = "Start Capture"
                self.title = "C"
                self._status_item.title = "Status: Stopped"
            else:
                # Check screen recording permission first
                from .permissions import check_screen_recording_permission
                if not check_screen_recording_permission():
                    rumps.notification(
                        title="Coachy",
                        subtitle="Permission Required",
                        message=(
                            "Screen Recording permission is required. "
                            "Open System Settings > Privacy & Security > "
                            "Screen Recording and enable Coachy."
                        ),
                    )
                    return

                reset_config()  # re-read config in case user changed it
                self._daemon.start()
                sender.title = "Stop Capture"
                self.title = "C*"
                self._status_item.title = "Status: Running"
        except Exception as exc:
            rumps.notification("Coachy", "Error", friendly_error(exc))

    def _daily_digest(self, _sender):
        self._run_digest("day")

    def _weekly_digest(self, _sender):
        self._run_digest("week")

    def _run_digest(self, period: str):
        """Generate a digest in a background thread, save to file, and open it."""
        def _work():
            try:
                import subprocess
                from .app_paths import get_digests_dir
                from .coach.digest import DigestGenerator

                config = get_config()
                persona = config.get("coach.default_persona", "grove")

                generator = DigestGenerator()
                content = generator.generate_digest(period=period, persona=persona)

                # Save to file with timestamp to avoid overwrites
                digests_dir = get_digests_dir()
                timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                filename = f"{timestamp}_{period}.md"
                filepath = digests_dir / filename
                filepath.write_text(content, encoding="utf-8")

                # Open in default app
                subprocess.Popen(["open", str(filepath)])

                rumps.notification(
                    title="Coachy Digest",
                    subtitle=f"{period.title()} digest ready",
                    message=f"Saved to {filename}",
                )

            except Exception as exc:
                rumps.notification("Coachy", "Digest failed", friendly_error(exc))

        t = threading.Thread(target=_work, name="coachy-digest", daemon=True)
        t.start()

    def _open_settings(self, _sender):
        try:
            if self._settings_controller is None:
                from .settings_window import SettingsWindowController
                self._settings_controller = SettingsWindowController()
            self._settings_controller.show()
        except Exception as exc:
            rumps.notification("Coachy", "Settings error", friendly_error(exc))

    def _quit(self, _sender):
        if self._daemon.is_running():
            self._daemon.stop(timeout=5)
        rumps.quit_application()

    # ---- status polling ----

    def _poll_status(self, _timer):
        """Periodically update the status menu item."""
        try:
            if self._daemon.is_running():
                config = get_config()
                db = get_database(config.db_path)
                now = int(datetime.now().timestamp())
                day_ago = now - 86400
                summary = db.get_activity_summary(day_ago, now)
                count = summary.get("total_tracked_minutes", 0)
                self._status_item.title = f"Status: Running  |  {count}m today"

                # Update coach label
                persona = config.get("coach.default_persona", "grove")
                self._coach_label.title = f"Coach: {persona}"
            else:
                err = self._daemon.last_error
                if err:
                    self._status_item.title = f"Status: Error"
                # else leave as-is (Stopped)
        except Exception:
            pass  # never crash the timer

    def _on_daemon_error(self, exc: Exception):
        """Called from the daemon thread when it crashes."""
        rumps.notification("Coachy", "Capture stopped", friendly_error(exc))


def main():
    """Entry point for the menu bar app."""
    app = CoachyApp()

    # First-run check
    if not get_config_path().exists():
        app._first_run_setup()

    app.run()


if __name__ == "__main__":
    main()
