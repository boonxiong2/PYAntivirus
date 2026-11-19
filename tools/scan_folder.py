"""扫描文件夹，生成MD5哈希库"""
import hashlib, json, os, sys

folder = sys.argv[1] if len(sys.argv) > 1 else "."
out = sys.argv[2] if len(sys.argv) > 2 else "my_virus_hashes.txt"

hashes = set()
count = 0

for root, dirs, files in os.walk(folder):
    for f in files:
        path = os.path.join(root, f)
        try:
            size = os.path.getsize(path)
            if size > 100 * 1024 * 1024:  # 跳过100MB+
                continue
            with open(path, 'rb') as fh:
                h = hashlib.md5(fh.read()).hexdigest()
            hashes.add(h)
            count += 1
            if count % 100 == 0:
                print(f"\r已处理: {count} 个文件...", end="")
        except:
            pass

with open(out, 'w') as f:
    for h in sorted(hashes):
        f.write(h + '\n')

print(f"\n完成！{count} 个文件 → {len(hashes)} 个唯一哈希 → {out}")
