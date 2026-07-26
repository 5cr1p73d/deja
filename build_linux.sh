#!/usr/bin/env bash
# Build Linux di Déjà (Fase 1, target X11).
# Da eseguire SU LINUX (Ubuntu 22.04+ consigliato per compatibilità glibc).
#
# Prerequisiti di sistema:
#   sudo apt install -y python3.12 python3.12-venv build-essential \
#        portaudio19-dev tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng \
#        xdotool libxss1 libsecret-1-0 gnome-keyring \
#        libxcb-cursor0   # richiesto da Qt6 su alcune distro
#
# Output: dist/Deja/ (onedir) + deja-<ver>-linux-x86_64.tar.gz
set -euo pipefail
cd "$(dirname "$0")"

PY=${PY:-python3}
VER=$($PY -c "import re;print(re.search(r'APP_VERSION\s*=\s*\"([^\"]+)\"',open('config.py',encoding='utf-8').read()).group(1))")

echo "== Déjà $VER — build Linux =="

if [ ! -d venv-linux ]; then
  $PY -m venv venv-linux
fi
# shellcheck disable=SC1091
source venv-linux/bin/activate
pip install --upgrade pip wheel
# I marker in requirements.txt installano solo le dipendenze Linux
# (PyAudio/pynput/keyring; niente pyaudiowpatch/winrt/pygetwindow).
pip install -r requirements.txt

echo "== PyInstaller =="
pyinstaller deja.spec --noconfirm

echo "== Archivio portable =="
OUT="deja-${VER}-linux-x86_64.tar.gz"
tar -C dist -czf "$OUT" Deja
echo "OK → $OUT"

cat <<'EOF'

Note:
- Primo avvio: ./dist/Deja/Deja
- Wayland: la cattura schermo richiede X11 (o sessione Xorg). Su Wayland puro
  avviare con: QT_QPA_PLATFORM=xcb e sessione X11 — supporto Wayland = fase 2.
- AppImage (opzionale): usare appimagetool su dist/Deja con un AppRun che
  esegue ./Deja e il .desktop in assets/. Vedi obsidian/deja/Linux.md.
EOF
