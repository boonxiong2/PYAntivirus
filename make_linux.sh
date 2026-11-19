#!/bin/bash
# PYAntivirus Linux Build Script
set -e

echo "========================================"
echo "  PYAntivirus Linux Build"
echo "========================================"

PROJ="/mnt/c/Users/Administrator/PycharmProjects/PythonProject"
BUILD="/tmp/pyav-build"
rm -rf "$BUILD"
mkdir -p "$BUILD"

# Copy source to Linux-native filesystem (needed for permissions)
cp -r "$PROJ/src" "$BUILD/"
cp -r "$PROJ/resources" "$BUILD/"

cd "$BUILD"

echo "[0/3] Installing deps..."
sudo apt install -y python3-venv python3-tk 2>/dev/null
python3 -m venv .venv
source .venv/bin/activate
pip install -q pyinstaller customtkinter pystray pillow watchdog pefile psutil numpy

echo "[1/3] Building PYAntivirus (ELF)..."
pyinstaller --onefile --windowed \
  --name "PYAntivirus" \
  --add-data "resources/icon.png:resources" \
  --add-data "resources/virus_hash_lib.txt:resources" \
  --hidden-import customtkinter \
  --hidden-import pystray \
  --hidden-import PIL \
  --hidden-import PIL.Image \
  --hidden-import watchdog \
  --hidden-import pefile \
  --hidden-import psutil \
  --hidden-import numpy \
  src/PYAntivirus_linux.py

echo "[2/3] Building .deb..."
mkdir -p deb/DEBIAN
mkdir -p deb/usr/bin
mkdir -p deb/usr/share/pyav/resources
mkdir -p deb/usr/share/applications

chmod 755 deb/DEBIAN

cp dist/PYAntivirus deb/usr/bin/
cp resources/icon.png resources/virus_hash_lib.txt deb/usr/share/pyav/resources/

cat > deb/usr/share/applications/pyav.desktop << 'EOF'
[Desktop Entry]
Name=PYAntivirus
Comment=Python Smart Antivirus
Exec=/usr/bin/PYAntivirus
Icon=/usr/share/pyav/resources/icon.png
Type=Application
Categories=System;Security;
EOF

cat > deb/DEBIAN/control << EOF
Package: pyav
Version: 3.3
Section: utils
Priority: optional
Architecture: amd64
Depends: python3
Maintainer: PYAntivirus Security
Description: Python Smart Antivirus
 110万病毒库 · 8层检测引擎 · ML检测
EOF

dpkg-deb --build deb pyav_3.3_amd64.deb

# Copy result back to Windows
cp pyav_3.3_amd64.deb "$PROJ/dist/"

echo ""
echo "========================================"
echo "  Done! dist/pyav_3.3_amd64.deb"
echo "========================================"
