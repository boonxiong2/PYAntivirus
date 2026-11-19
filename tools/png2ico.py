#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PNG → ICO 转换器"""
import sys
from PIL import Image

def png2ico(png_path, ico_path=None):
    if ico_path is None:
        ico_path = png_path.rsplit('.', 1)[0] + '.ico'

    img = Image.open(png_path)

    # ICO 需要这些尺寸
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]

    img.save(ico_path, format='ICO', sizes=[s for s in sizes if s[0] <= img.width])

    print(f"✓ {png_path} → {ico_path}")
    print(f"  包含尺寸: {[s for s in sizes if s[0] <= img.width]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python png2ico.py icon.png [icon.ico]")
        sys.exit(1)

    png = sys.argv[1]
    ico = sys.argv[2] if len(sys.argv) > 2 else None
    png2ico(png, ico)
