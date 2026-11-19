import os
import hashlib
import json

import easygui


def calculate_file_hash(file_path, algorithm='md5'):
    """计算单个文件的哈希值"""
    hash_func = hashlib.md5() if algorithm == 'md5' else hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            # 分块读取大文件，避免内存占用过高
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        print(f"计算文件 {file_path} 哈希时出错: {e}")
        return None

def build_hash_database(folder_path, output_json='virus_hash_db.json', algorithm='md5'):
    """遍历文件夹，构建哈希数据库"""
    hash_database = {}

    for root, dirs, files in os.walk(folder_path):
        for file_name in files:
            file_full_path = os.path.join(root, file_name)
            print(f"[*] 正在处理: {file_full_path}")
            file_hash = calculate_file_hash(file_full_path, algorithm)

            if file_hash:
                # 使用相对路径或绝对路径作为键。这里使用绝对路径确保唯一性。
                hash_database[file_full_path] = {
                    'hash': file_hash,
                    'algorithm': algorithm
                }

    # 将数据库保存为JSON文件
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(hash_database, f, indent=4, ensure_ascii=False)

    print(f"\n[+] 完成！共处理 {len(hash_database)} 个文件。")
    print(f"[+] 哈希数据库已保存至: {output_json}")
    return hash_database

if __name__ == '__main__':
    # ==== 配置部分 ====
    # 1. 修改为你的病毒样本存放目录
    target_folder = easygui.diropenbox()
    # 2. 修改为你想要的输出JSON文件名
    output_file = "virus_hash_lib2.json"
    # 3. 选择哈希算法：'md5' 或 'sha256'
    hash_algorithm = 'md5'
    # ==================

    # 执行构建
    db = build_hash_database(target_folder, output_file, hash_algorithm)