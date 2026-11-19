# -*- coding: utf-8 -*-
"""
PYAntivirus 病毒库更新器（多源）
用法: python tools/update_virus_db.py

源（按顺序，挂了自动切下一个，全挂保留旧库）:
  1. MalwareBazaar get_recent        —— 近 60 分钟新增样本
  2. MalwareBazaar get_taginfo        —— 指定家族定向拉取（银狐/远控/挖矿/勒索）
  3. MalwareBazaar recent_detections  —— 近 N 小时有家族标签的样本

API key 获取: https://mb-api.abuse.ch（免费，个人用途）
存放方式: 环境变量 MB_API_KEY 或 文件 ~/.mb_api_key（一行，别提交进仓库）

安全:
  - 写入前备份旧库（.bak），写坏不覆盖
  - 只追加新 md5，绝不缩库
"""
import json
import os
import sys
import time
import requests

API = "https://mb-api.abuse.ch/api/v1/"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "virus_hash_lib.txt")

# 请求节流（秒）：abuse.ch fair-use，慢一点换稳
THROTTLE = 2.0

# 定向狩猎的家族标签（MalwareBazaar tag，拉不到的非致命跳过）
# 银狐系 + 流行 RAT/窃密 + 挖矿/勒索
FAMILY_TAGS = [
    # 银狐 / 国内流行
    "silverfox", "SilverFox", "gh0st", "ValleyRAT", "Winos", "PurpleFox",
    # 远程控制 RAT
    "remcos", "njrat", "xworm", "asyncrat", "quasar", "dcrat", "venomrat",
    "nanocore", "adwind", "orcusrat", "warzone",
    # 窃密木马
    "formbook", "agenttesla", "redline", "raccoon", "vidar", "lumma",
    "stealc", "arkei", "remus", "risepro",
    # 加载器 / 银行木马
    "amadey", "smokeloader", "qakbot", "icedid", "dridex", "guloader",
    # 挖矿
    "xmrig", "coinhive", "nanopool",
    # 勒索
    "wannacry", "lockbit", "conti", "blackcat", "clop", "phobos",
    # 渗透框架
    "cobaltstrike", "metasploit",
]


def api_key():
    """读取 API key：环境变量优先，其次 ~/.mb_api_key"""
    k = os.environ.get("MB_API_KEY", "")
    if not k:
        p = os.path.join(os.path.expanduser("~"), ".mb_api_key")
        if os.path.exists(p):
            k = open(p, encoding="utf-8").read().strip()
    return k


def query(data, key, retries=3):
    """POST form 请求 MalwareBazaar API，带重试退避（跨境 TLS 掐断 + 429 限流）"""
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(API, data=data, headers={"Auth-Key": key}, timeout=30)
            if resp.status_code == 429:
                wait = 60
                print(f"    ⚠ 429 限流，等 {wait}s 后重试")
                time.sleep(wait)
                last_err = RuntimeError("HTTP 429 Too Many Requests")
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败({retries}次重试): {last_err}")


def extract_md5s(payload):
    """从 API 响应里抠 md5（我们的库是 md5 匹配）"""
    return {e["md5_hash"].lower() for e in payload.get("data", []) if e.get("md5_hash")}


def fetch_recent(key):
    """源1: 近 60 分钟新增"""
    d = query({"query": "get_recent", "selector": "time"}, key)
    if d.get("query_status") != "ok":
        raise RuntimeError(f"get_recent: {d.get('query_status')}")
    return extract_md5s(d)


def fetch_family(key, tag):
    """源2: 按家族标签拉样本（标签不存在返回空集，不致命）"""
    d = query({"query": "get_taginfo", "tag": tag, "limit": "1000"}, key)
    if d.get("query_status") != "ok":
        print(f"    ⚠ {tag}: {d.get('query_status')}（跳过）")
        return set()
    return extract_md5s(d)


def fetch_detections(key, hours=168):
    """源3: 近 N 小时有家族标签的样本（API 上限 168h = 7 天，一次拉满）"""
    d = query({"query": "recent_detections", "hours": str(hours)}, key)
    if d.get("query_status") != "ok":
        raise RuntimeError(f"recent_detections: {d.get('query_status')}")
    return extract_md5s(d)


def load_existing():
    """读旧库（损坏时返回空，绝不崩溃）"""
    if not os.path.exists(DB_PATH):
        return set()
    try:
        with open(DB_PATH, "r", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if len(line.strip()) == 32}
    except Exception as e:
        print(f"[!] 旧库读取失败: {e}")
        return set()


def main():
    key = api_key()
    if not key:
        print("[!] 未找到 API key")
        print("    1. 去 https://mb-api.abuse.ch 注册获取")
        print("    2. 存到 ~/.mb_api_key（一行）或设置环境变量 MB_API_KEY")
        sys.exit(1)

    print(f"[*] 病毒库: {os.path.normpath(DB_PATH)}")
    existing = load_existing()
    print(f"[*] 现有: {len(existing)} 条")

    new_hashes = set()
    sources_ok = 0

    # 源1: 近 60 分钟新增
    try:
        got = fetch_recent(key)
        new_hashes |= got
        sources_ok += 1
        print(f"[✓] MalwareBazaar 近60分钟: {len(got)} 条")
    except Exception as e:
        print(f"[✗] get_recent 失败: {e}")

    # 源2: 家族定向狩猎（节流防 429）
    for tag in FAMILY_TAGS:
        try:
            got = fetch_family(key, tag)
            if got:
                new_hashes |= got
                print(f"[✓] 家族 {tag}: {len(got)} 条")
            time.sleep(THROTTLE)
        except Exception as e:
            print(f"[✗] {tag} 查询失败: {e}")
            time.sleep(THROTTLE)

    # 源3: 近 7 天有家族标签的样本
    try:
        got = fetch_detections(key, 168)
        new_hashes |= got
        sources_ok += 1
        print(f"[✓] 近7天检测样本: {len(got)} 条")
    except Exception as e:
        print(f"[✗] recent_detections 失败: {e}")

    if sources_ok == 0 and not new_hashes:
        print("[!] 所有源都失败——保留旧库（last-known-good）")
        sys.exit(2)

    added = new_hashes - existing
    if not added:
        print("[✓] 没有新哈希，库已是最新")
        return

    merged = existing | added
    # 备份旧库 → 原子写入（先写 tmp 再替换，写坏不伤旧库）
    bak = DB_PATH + ".bak"
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "rb") as src, open(bak, "wb") as dst:
                dst.write(src.read())
        except Exception as e:
            print(f"[!] 备份失败（继续）: {e}")
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(merged)) + "\n")
    os.replace(tmp, DB_PATH)

    print(f"\n[✓] 新增 {len(added)} 条，库总计 {len(merged)} 条")
    print(f"[✓] 备份: {os.path.basename(bak)}")
    print("\n提示: 更新后重跑 make.bat 重新打包，或源码跑直接生效（加载的是 resources/ 下文件）")


if __name__ == "__main__":
    main()
