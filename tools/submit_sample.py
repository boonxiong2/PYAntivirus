# -*- coding: utf-8 -*-
"""
PYAntivirus 恶意样本提交器（MalwareBazaar 贡献端）
用法: python tools/submit_sample.py <文件路径> [--tag exe] [--no-anonymous]

API key 与 update_virus_db.py 共用: ~/.mb_api_key 或环境变量 MB_API_KEY

⚠️ 提交政策（违反会被封号，务必遵守）:
  1. 只提交【确认】的恶意软件——启发式"可疑"不算数，别提交
  2. 不提交广告软件/PUP
  3. 只提交 10 天内的新样本
  4. 不提交文件感染者
默认匿名提交（anonymous=1），保护你的隐私。
"""
import argparse
import json
import os
import sys
import requests

API = "https://mb-api.abuse.ch/api/v1/"


def api_key():
    k = os.environ.get("MB_API_KEY", "")
    if not k:
        p = os.path.join(os.path.expanduser("~"), ".mb_api_key")
        if os.path.exists(p):
            k = open(p, encoding="utf-8").read().strip()
    return k


def submit(auth_key, file_path, anonymous=True, tags=None):
    """multipart 上传（和官方 submit_sample.py 同款）"""
    json_data = {"anonymous": 1 if anonymous else 0}
    if tags:
        json_data["tags"] = tags
    files = {
        "json_data": (None, json.dumps(json_data), "application/json"),
        "file": (os.path.basename(file_path), open(file_path, "rb"), "application/octet-stream"),
    }
    resp = requests.post(API, files=files, headers={"Auth-Key": auth_key}, timeout=120)
    resp.raise_for_status()
    return resp.text


def main():
    parser = argparse.ArgumentParser(description="提交恶意样本到 MalwareBazaar")
    parser.add_argument("file", help="要提交的恶意样本文件")
    parser.add_argument("--tag", action="append", default=[], help="标签（可多次），如 --tag exe --tag silverfox")
    parser.add_argument("--no-anonymous", action="store_true", help="不匿名（会显示你的上报者名）")
    args = parser.parse_args()

    key = api_key()
    if not key:
        print("[!] 未找到 API key: 写入 ~/.mb_api_key 或设置 MB_API_KEY")
        sys.exit(1)
    if not os.path.isfile(args.file):
        print(f"[!] 文件不存在: {args.file}")
        sys.exit(1)

    size = os.path.getsize(args.file)
    print(f"[*] 提交: {args.file} ({size/1024:.1f} KB)")
    print(f"[*] 匿名: {'是' if not args.no_anonymous else '否'}  标签: {args.tag or '无'}")
    print("[!] 再次确认: 这是【确认的恶意软件】且【10天内】的新样本？(Ctrl+C 取消)")

    try:
        resp = submit(key, args.file, anonymous=not args.no_anonymous, tags=args.tag or None)
    except Exception as e:
        print(f"[✗] 提交失败: {e}")
        sys.exit(1)

    print(f"\n=== 服务器响应 ===\n{resp}")
    if '"query_status": "inserted"' in resp or "inserted" in resp:
        print("\n[✓] 样本已入库，全球情报池 +1")
    elif "file_already_known" in resp:
        print("\n[ℹ] 该样本已存在")


if __name__ == "__main__":
    main()
