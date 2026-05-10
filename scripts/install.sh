#!/bin/bash
# AnberCC installer dla Anbernic RG40XX V
# Uruchom z root (lub sudo) na konsoli — przez SSH lub terminal
set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APPS_DIR="/mnt/mmc/Roms/APPS"
APP_DIR="$APPS_DIR/anbercc"
IMGS_DIR="$APPS_DIR/Imgs"

echo "=== AnberCC install ==="

# 1. SDL2 app
mkdir -p "$APP_DIR"
cp "$REPO_DIR/app/main.py" "$APP_DIR/main.py"
cp "$REPO_DIR/app/AnberCC.sh" "$APPS_DIR/AnberCC.sh"
chmod +x "$APPS_DIR/AnberCC.sh"
echo "✓ App skopiowane do $APP_DIR"

# 2. Ikona (generowana w PIL)
mkdir -p "$IMGS_DIR"
python3 - <<EOF
from PIL import Image, ImageDraw
img = Image.new('RGBA', (240, 180), (0,0,0,0))
d = ImageDraw.Draw(img)
d.rectangle([(0,0),(240,180)], fill=(15,20,35,255))
# stylizowany prompt ">_"
d.rectangle([(60,50),(180,130)], outline=(80,180,255,255), width=4)
d.text((78, 70), '> _', fill=(80,220,100,255))
img.save('$IMGS_DIR/AnberCC.png')
EOF
echo "✓ Ikona w $IMGS_DIR/AnberCC.png"

# 3. Sprawdź zależności
python3 -c "import sdl2" 2>/dev/null || echo "⚠️  brak pysdl2 — pip install pysdl2"
python3 -c "import pyte" 2>/dev/null || echo "⚠️  brak pyte — pip install pyte"
python3 -c "import PIL" 2>/dev/null || echo "⚠️  brak Pillow — pip install Pillow"

# 4. Sprawdź Claude CLI
if [ ! -x /root/.local/bin/claude ] && ! command -v claude >/dev/null; then
    echo "⚠️  brak claude CLI — zainstaluj:"
    echo "    npm install -g @anthropic-ai/claude-code"
    echo "    claude login"
fi

echo ""
echo "Zainstalowane. Uruchom 'AnberCC' z App Center."
