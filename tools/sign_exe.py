"""构建辅助：给已构建的 EXE 记录 SHA256 签名到 integrity.json"""
import hashlib, json, os

exe_path = os.path.join('dist', 'PYAntivirus.exe')
integrity_path = os.path.join('resources', 'integrity.json')

if not os.path.exists(exe_path):
    print(f"SKIP: {exe_path} not found")
    exit(0)

# 计算 EXE 哈希
with open(exe_path, 'rb') as f:
    h = hashlib.sha256(f.read()).hexdigest()[:16]

# 写入 integrity.json
manifest = {}
if os.path.exists(integrity_path):
    with open(integrity_path) as f:
        manifest = json.load(f)

manifest['PYAntivirus.exe'] = h
with open(integrity_path, 'w') as f:
    json.dump(manifest, f, indent=2)

print(f"EXE signature: {h}")
