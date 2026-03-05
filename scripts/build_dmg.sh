#!/usr/bin/env bash
#
# Build Coachy.app and package it into a .dmg for distribution.
#
# Usage:  ./scripts/build_dmg.sh
#
# Requires: Python 3.9+, pip, hdiutil (macOS built-in)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_ENV="$PROJECT_DIR/.buildenv"
DIST_DIR="$PROJECT_DIR/dist"
DMG_NAME="Coachy.dmg"

echo "==> Cleaning previous build artifacts..."
rm -rf "$PROJECT_DIR/build" "$DIST_DIR" "$BUILD_ENV"

echo "==> Creating virtual environment..."
python3 -m venv "$BUILD_ENV"
source "$BUILD_ENV/bin/activate"

echo "==> Installing project and build dependencies..."
pip install --upgrade pip setuptools wheel
pip install -e "$PROJECT_DIR"
pip install py2app rumps keyring

echo "==> Building Coachy.app with py2app..."
cd "$PROJECT_DIR"
python3 setup_app.py py2app

echo "==> Verifying app bundle..."
APP_PATH="$DIST_DIR/Coachy.app"
if [ ! -d "$APP_PATH" ]; then
    echo "ERROR: $APP_PATH was not created"
    exit 1
fi
echo "    App bundle: $APP_PATH"
echo "    Size: $(du -sh "$APP_PATH" | cut -f1)"

echo "==> Creating DMG..."
DMG_STAGING="$PROJECT_DIR/build/dmg_staging"
mkdir -p "$DMG_STAGING"
cp -R "$APP_PATH" "$DMG_STAGING/"
ln -s /Applications "$DMG_STAGING/Applications"

hdiutil create \
    -volname "Coachy" \
    -srcfolder "$DMG_STAGING" \
    -ov \
    -format UDZO \
    "$DIST_DIR/$DMG_NAME"

echo ""
echo "==> Build complete!"
echo "    DMG: $DIST_DIR/$DMG_NAME"
echo "    Size: $(du -sh "$DIST_DIR/$DMG_NAME" | cut -f1)"
echo ""
echo "To test: open $DIST_DIR/$DMG_NAME"

deactivate
