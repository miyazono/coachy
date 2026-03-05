"""Centralized path resolution for Coachy.

All runtime data lives under ~/Library/Application Support/Coachy/ on macOS.
This module resolves paths regardless of CWD, whether running from CLI or .app bundle.
"""
import os
import pathlib
import sys


def _is_frozen() -> bool:
    """Check if running from a py2app .app bundle."""
    return getattr(sys, 'frozen', False)


def get_app_dir() -> pathlib.Path:
    """Return the main application data directory, creating it if needed.

    Returns:
        ~/Library/Application Support/Coachy/
    """
    app_dir = pathlib.Path.home() / "Library" / "Application Support" / "Coachy"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> pathlib.Path:
    """Return path to config.yaml."""
    return get_app_dir() / "config.yaml"


def get_config_example_path() -> pathlib.Path:
    """Return path to the bundled config.yaml.example.

    When running from a .app bundle, looks in the bundle's Resources directory.
    When running in dev mode, looks relative to the project root.
    """
    return get_bundle_resources_dir() / "config.yaml.example"


def get_db_path() -> pathlib.Path:
    """Return path to the SQLite database."""
    db_dir = get_app_dir() / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "coachy.db"


def get_screenshots_path() -> pathlib.Path:
    """Return path to the screenshots directory."""
    screenshots_dir = get_app_dir() / "data" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return screenshots_dir


def get_log_path() -> pathlib.Path:
    """Return path to the log file."""
    log_dir = get_app_dir() / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "coachy.log"


def get_pid_path() -> pathlib.Path:
    """Return path to the daemon PID file."""
    return get_app_dir() / "coachy.pid"


def get_personas_dir() -> pathlib.Path:
    """Return path to the personas directory."""
    personas_dir = get_app_dir() / "personas"
    personas_dir.mkdir(parents=True, exist_ok=True)
    return personas_dir


def get_private_personas_dir() -> pathlib.Path:
    """Return path to the private personas directory."""
    private_dir = get_app_dir() / "private-personas"
    private_dir.mkdir(parents=True, exist_ok=True)
    return private_dir


def get_digests_dir() -> pathlib.Path:
    """Return path to the digests directory."""
    digests_dir = get_app_dir() / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    return digests_dir


def get_priorities_path() -> pathlib.Path:
    """Return path to priorities.md."""
    return get_app_dir() / "priorities.md"


def get_bundle_resources_dir() -> pathlib.Path:
    """Return the directory containing bundled default files.

    When running from a .app bundle (py2app), this is the Resources dir
    inside the bundle. In dev mode, it's the project root (parent of coachy/).
    """
    if _is_frozen():
        # py2app sets sys.executable to the bundle's Python
        # Resources dir is: Coachy.app/Contents/Resources/
        return pathlib.Path(os.environ.get(
            'RESOURCEPATH',
            pathlib.Path(sys.executable).parent.parent / "Resources"
        ))
    else:
        # Dev mode: project root is one level up from coachy/ package
        return pathlib.Path(__file__).parent.parent
