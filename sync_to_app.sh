#!/bin/bash
# sync_to_app.sh — Copy source files into the .app bundle
# Run this after making any code changes to push them into the packaged app.

set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
BUNDLE="$SRC/OpenChat Local.app/Contents/Resources/app"

echo "🔄  Syncing source → .app bundle..."
echo "    Source:  $SRC"
echo "    Bundle:  $BUNDLE"
echo ""

# ── Core Python backend ─────────────────────────────────────────
echo "  [1/5] main.py & config.py..."
cp "$SRC/main.py"   "$BUNDLE/main.py"
cp "$SRC/config.py" "$BUNDLE/config.py"

# ── Python packages ─────────────────────────────────────────────
echo "  [2/5] core/ routes/ utils/ packages..."
rsync -a --exclude='__pycache__' "$SRC/core/"   "$BUNDLE/core/"
rsync -a --exclude='__pycache__' "$SRC/routes/" "$BUNDLE/routes/" 2>/dev/null || true
rsync -a --exclude='__pycache__' "$SRC/utils/"  "$BUNDLE/utils/"

# ── Frontend: templates ──────────────────────────────────────────
echo "  [3/5] templates/..."
rsync -a "$SRC/templates/" "$BUNDLE/templates/"

# ── Frontend: static (JS / CSS / assets) ────────────────────────
echo "  [4/5] static/..."
rsync -a "$SRC/static/" "$BUNDLE/static/"

# ── Requirements (optional) ──────────────────────────────────────
echo "  [5/5] requirements.txt..."
cp "$SRC/requirements.txt" "$BUNDLE/requirements.txt"

echo ""
echo "✅  Sync complete! Restart the app to see your changes."
