#!/usr/bin/env bash
# build_app.sh — Build OpenChat Local.app (fully self-contained)
# Usage: ./build_app.sh
# Requires: Xcode Command Line Tools (xcode-select --install)

set -euo pipefail

APP_NAME="OpenChat Local"
BINARY_NAME="OpenChatLocal"
APP_DIR="${APP_NAME}.app"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "  ◭  Building ${APP_NAME}…"
echo ""

# ── 1. Compile Swift ──────────────────────────────────────────────────────────

echo "  [1/5] Compiling Swift source…"
swiftc \
  -sdk "$(xcrun --show-sdk-path)" \
  -target arm64-apple-macosx13.0 \
  -framework Cocoa \
  -framework WebKit \
  -O \
  "${SCRIPT_DIR}/OpenChatLocal.swift" \
  -o "${SCRIPT_DIR}/${BINARY_NAME}"

echo "        Done ✓"

# ── 2. Create .app bundle structure ───────────────────────────────────────────

echo "  [2/5] Creating .app bundle…"

rm -rf "${SCRIPT_DIR}/${APP_DIR}"

mkdir -p "${SCRIPT_DIR}/${APP_DIR}/Contents/MacOS"
mkdir -p "${SCRIPT_DIR}/${APP_DIR}/Contents/Resources"
mkdir -p "${SCRIPT_DIR}/${APP_DIR}/Contents/Resources/app"

# Copy binary
cp "${SCRIPT_DIR}/${BINARY_NAME}" "${SCRIPT_DIR}/${APP_DIR}/Contents/MacOS/${BINARY_NAME}"
chmod +x "${SCRIPT_DIR}/${APP_DIR}/Contents/MacOS/${BINARY_NAME}"

# Copy Info.plist
cp "${SCRIPT_DIR}/OpenChatLocal.plist" "${SCRIPT_DIR}/${APP_DIR}/Contents/Info.plist"

echo "        Done ✓"

# ── 3. Embed Python app inside bundle ─────────────────────────────────────────

echo "  [3/5] Embedding Python app into bundle…"

APP_RESOURCES="${SCRIPT_DIR}/${APP_DIR}/Contents/Resources/app"

# Copy all project files (excluding the .app itself and build artifacts)
rsync -a \
  --exclude="${APP_DIR}" \
  --exclude="${BINARY_NAME}" \
  --exclude="*.pyc" \
  --exclude="__pycache__" \
  --exclude=".git" \
  --exclude=".venv" \
  --exclude="venv" \
  --exclude="AppIcon.iconset" \
  "${SCRIPT_DIR}/" \
  "${APP_RESOURCES}/"

# ── Install Python dependencies into bundled venv ──────────────────────────

PYTHON3=$(which python3 || echo "/opt/homebrew/bin/python3")
VENV_DIR="${APP_RESOURCES}/.venv"

echo "        Creating bundled Python venv…"
"${PYTHON3}" -m venv "${VENV_DIR}"

echo "        Installing dependencies (this may take a few minutes)…"
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${APP_RESOURCES}/requirements.txt"

echo "        Done ✓"

# ── 4. Generate .icns icon ────────────────────────────────────────────────────

echo "  [4/5] Generating app icon…"

ICONSET="${SCRIPT_DIR}/AppIcon.iconset"
mkdir -p "${ICONSET}"

python3 - "${ICONSET}" <<'PYEOF'
import sys, os, struct, zlib

iconset = sys.argv[1]

def make_simple_icon(size, path):
    def png_chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    pixels = []
    bg = (18, 18, 18)
    ac = (210, 208, 202)
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            cx, cy = size / 2.0, size / 2.0
            dx, dy = abs(x - cx), abs(y - cy)
            
            # Squircle alpha
            r_cornerRadius = size * 0.225
            inner_w = size / 2.0 - r_cornerRadius
            dist_x = max(0.0, dx - inner_w)
            dist_y = max(0.0, dy - inner_w)
            dist_from_corner = (dist_x**2 + dist_y**2)**0.5
            
            alpha = 255.0
            if dist_from_corner > r_cornerRadius:
                alpha = max(0.0, 255.0 - (dist_from_corner - r_cornerRadius) * 255.0)
            
            alpha_int = max(0, min(255, int(alpha)))
            
            # Diamond outline
            r_diamond = size * 0.35
            stroke = size * 0.08
            dist_center = dx + dy
            
            diamond_alpha = 0.0
            if r_diamond - stroke <= dist_center <= r_diamond:
                diamond_alpha = 1.0
            elif abs(dist_center - r_diamond) < 1.0:
                diamond_alpha = max(0.0, 1.0 - abs(dist_center - r_diamond))
            elif abs(dist_center - (r_diamond - stroke)) < 1.0:
                diamond_alpha = max(0.0, 1.0 - abs(dist_center - (r_diamond - stroke)))
                
            r = int(ac[0] * diamond_alpha + bg[0] * (1-diamond_alpha))
            g = int(ac[1] * diamond_alpha + bg[1] * (1-diamond_alpha))
            b = int(ac[2] * diamond_alpha + bg[2] * (1-diamond_alpha))
            
            # apply pre-multiplied alpha if needed? No, standard RGBA
            row.extend([r, g, b, alpha_int])
        pixels.append(bytes(row))
        
    raw = b''.join(pixels)
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0) # 6 = RGBA
    png  = b'\x89PNG\r\n\x1a\n'
    png += png_chunk(b'IHDR', ihdr)
    png += png_chunk(b'IDAT', compressed)
    png += png_chunk(b'IEND', b'')
    with open(path, 'wb') as f: f.write(png)

for s in [16, 32, 64, 128, 256, 512, 1024]:
    make_simple_icon(s, f'{iconset}/icon_{s}x{s}.png')
    if s <= 512:
        make_simple_icon(s * 2, f'{iconset}/icon_{s}x{s}@2x.png')
print("Icons generated")
PYEOF

if iconutil -c icns "${ICONSET}" -o "${SCRIPT_DIR}/${APP_DIR}/Contents/Resources/AppIcon.icns" 2>/dev/null; then
    /usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" \
        "${SCRIPT_DIR}/${APP_DIR}/Contents/Info.plist" 2>/dev/null || true
fi

rm -rf "${ICONSET}"
echo "        Done ✓"

# ── 5. Clean up intermediate files ────────────────────────────────────────────

echo "  [5/5] Cleaning up…"
rm -f "${SCRIPT_DIR}/${BINARY_NAME}"
echo "        Done ✓"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ✅  Built: ${SCRIPT_DIR}/${APP_DIR}"
echo ""
echo "  Bundle size: $(du -sh "${SCRIPT_DIR}/${APP_DIR}" | cut -f1)"
echo ""
echo "  To install: drag '${APP_NAME}.app' to /Applications"
echo "  To run now: open '${SCRIPT_DIR}/${APP_DIR}'"
echo ""
echo "  NOTE: The app is now fully self-contained — the Python app and"
echo "        all dependencies are embedded inside the .app bundle."
echo "        No external Python installation or project folder required."
echo ""

# Auto-open the app
read -rp "  Open the app now? [Y/n] " answer
if [[ "${answer}" != "n" && "${answer}" != "N" ]]; then
    open "${SCRIPT_DIR}/${APP_DIR}"
fi
