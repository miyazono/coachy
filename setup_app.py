"""py2app build configuration for Coachy.app menu bar application."""
from setuptools import setup

APP = ["coachy/menubar.py"]

DATA_FILES = [
    ("", ["config.yaml.example", "priorities.md.example"]),
    ("personas", ["personas/grove.md"]),
]

OPTIONS = {
    "argv_emulation": False,
    "iconfile": None,  # TODO: add an icon file (Coachy.icns)
    "plist": {
        "CFBundleName": "Coachy",
        "CFBundleDisplayName": "Coachy",
        "CFBundleIdentifier": "com.coachy.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "LSUIElement": True,  # menu-bar-only app, no Dock icon
        "NSScreenCaptureUsageDescription": (
            "Coachy captures periodic screenshots to analyze your work patterns "
            "and provide productivity coaching. All data stays on your Mac."
        ),
    },
    "packages": [
        "coachy",
        "rumps",
        "yaml",
        "anthropic",
        "keyring",
        "PIL",
    ],
    "includes": [
        "Quartz",
        "Vision",
        "AppKit",
        "objc",
        "Foundation",
        "CoreFoundation",
    ],
    "excludes": [
        "tkinter",
        "test",
        "unittest",
        "mlx_lm",
        "mlx",
    ],
}

setup(
    name="Coachy",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
