# -*- coding: utf-8 -*-
"""
自保护清单生成器 · 打包前运行（make.bat 的 [0/5] 步会自动调用）
用法: python tools\gen_integrity.py
作用: 计算资源文件的 SHA256 前缀，写入 resources\integrity.json
⚠ 注意: 更新病毒库 / 图标等资源后必须重新运行，否则自保护会误报"被篡改"

为什么不算 PYAntivirus.exe 本身:
    清单会被 --add-data 嵌进 exe，而清单里又存 exe 的哈希——
    两者互为因果（鸡生蛋），单次构建永远对不上，每次启动都会误报。
    exe 的保护交给签名 / 安装器，清单只管资源文件。
"""
import hashlib
import json
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根目录（脚本在 tools/ 下）
RES = os.path.join(BASE, "resources")

# make.bat 里 --add-data 打包进 exe 的资源都要列在这里
TARGETS = [
    "virus_hash_lib.txt",
    "virus_hash_lib.json",
    "icon.ico",
    "antivirus.ico",
    "icon.png",
    "NSudo.exe",
    "Minecraft.ttf",
]


def main():
    manifest = {}
    for name in TARGETS:
        path = os.path.join(RES, name)
        if not os.path.exists(path):
            print(f"⚠ 跳过（不存在）: {name}")
            continue
        with open(path, "rb") as f:
            manifest[name] = hashlib.sha256(f.read()).hexdigest()[:16]
        print(f"✓ {name} -> {manifest[name]}")

    out = os.path.join(RES, "integrity.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\n已写入 {out}（{len(manifest)} 个文件）")


if __name__ == "__main__":
    main()
