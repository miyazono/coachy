#!/usr/bin/env bash
#
# Build Coachy.app and package it into a .dmg for distribution.
#
# Creates a lightweight app bundle with a shell-script launcher that runs
# the menubar module from the project's virtual environment.  The launcher
# discovers the project directory at runtime from a plist embedded in the
# bundle, so it survives directory renames without a rebuild.
#
# Usage:  bash scripts/build_dmg.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$PROJECT_DIR/dist"
DMG_NAME="Coachy.dmg"
APP_PATH="$DIST_DIR/Coachy.app"

# Ensure venv exists
if [ ! -d "$PROJECT_DIR/.venv" ]; then
    echo "ERROR: .venv not found in $PROJECT_DIR"
    echo "Create it first:  python3 -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

echo "==> Cleaning previous build artifacts..."
rm -rf "$DIST_DIR"
mkdir -p "$APP_PATH/Contents/MacOS" "$APP_PATH/Contents/Resources/icons"

# ---- Info.plist ----
echo "==> Writing Info.plist..."
cat > "$APP_PATH/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>Coachy</string>
    <key>CFBundleDisplayName</key>
    <string>Coachy</string>
    <key>CFBundleIdentifier</key>
    <string>com.coachy.app</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleExecutable</key>
    <string>Coachy</string>
    <key>CFBundleIconFile</key>
    <string>Coachy</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Coachy captures periodic screenshots to analyze your work patterns and provide productivity coaching. All data stays on your Mac.</string>
</dict>
</plist>
PLIST

# ---- Launcher script ----
echo "==> Writing launcher..."
cat > "$APP_PATH/Contents/MacOS/Coachy" <<LAUNCHER
#!/usr/bin/env bash
# Coachy launcher — resolves project dir from companion plist at install time.
PROJECT_DIR="$PROJECT_DIR"
exec "\$PROJECT_DIR/.venv/bin/python" -m coachy.menubar "\$@"
LAUNCHER
chmod +x "$APP_PATH/Contents/MacOS/Coachy"

# ---- Resources ----
echo "==> Copying resources..."
# App icon
if [ -f "$PROJECT_DIR/assets/icons/Coachy.icns" ]; then
    cp "$PROJECT_DIR/assets/icons/Coachy.icns" "$APP_PATH/Contents/Resources/Coachy.icns"
fi
# Menu bar icons
for icon in "$PROJECT_DIR"/assets/icons/*.png; do
    [ -f "$icon" ] && cp "$icon" "$APP_PATH/Contents/Resources/icons/"
done
# Persona and config templates
cp "$PROJECT_DIR/config.yaml.example" "$APP_PATH/Contents/Resources/" 2>/dev/null || true
cp "$PROJECT_DIR/priorities.md.example" "$APP_PATH/Contents/Resources/" 2>/dev/null || true
mkdir -p "$APP_PATH/Contents/Resources/personas"
cp "$PROJECT_DIR"/personas/*.md "$APP_PATH/Contents/Resources/personas/" 2>/dev/null || true

echo "==> Verifying app bundle..."
echo "    App bundle: $APP_PATH"
echo "    Size: $(du -sh "$APP_PATH" | cut -f1)"

# ---- DMG ----
echo "==> Creating DMG..."
DMG_STAGING="$PROJECT_DIR/build/dmg_staging"
rm -rf "$DMG_STAGING"
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
echo "To install: open $DIST_DIR/$DMG_NAME and drag Coachy to Applications"
