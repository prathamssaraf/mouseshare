#!/usr/bin/env bash
# build_mac.sh — Build MouseShare.app for macOS
# Run from the project root: bash build/build_mac.sh

set -e
cd "$(dirname "$0")/.."

echo "==> Installing dependencies (Mac)"
pip install -r requirements-mac.txt

echo "==> Running PyInstaller"
pyinstaller \
  --name "MouseShare" \
  --windowed \
  --icon "assets/icon.icns" \
  --add-data "assets:assets" \
  --hidden-import "pynput.keyboard._darwin" \
  --hidden-import "pynput.mouse._darwin" \
  --hidden-import "pystray._darwin" \
  --hidden-import "PIL._tkinter_finder" \
  --osx-bundle-identifier "com.mouseshare.app" \
  "mouseshare/main.py"

echo ""
echo "==> Build complete: dist/MouseShare.app"
echo "    Drag to /Applications to install."
echo ""
echo "NOTE: For personal use between your own machines, no code signing is needed."
echo "      For public distribution, sign with:"
echo "      codesign --deep -o runtime -s 'Developer ID Application: ...' dist/MouseShare.app"
