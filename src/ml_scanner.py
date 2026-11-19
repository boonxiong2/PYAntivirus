# -*- coding: utf-8 -*-
"""
PYAntivirus 机器学习模块 · 人话版
┌─────────────────────────────────────────┐
│ 把文件当"体检报告"，提取13项指标        │
│ 熵值/节数量/加壳/TLS/可疑API...         │
│ → 100棵树投票 → 是病毒吗？0~100分      │
└─────────────────────────────────────────┘
"""
import os, math, json
from collections import Counter
import numpy as np


class MLScanner:
    """ML扫描器：有训练好的模型就用，没有就靠经验公式"""

    def __init__(self, model_path=None):
        self.model = None          # 训练好的模型
        self.feature_names = None  # 用了哪些特征
        self.means = None          # 特征平均值（用于标准化）
        self.stds = None           # 特征标准差
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)

    def load_model(self, path):
        """加载训练好的模型文件"""
        with open(path, 'r') as f:
            data = json.load(f)
        self.feature_names = data["feature_names"]
        self.means = np.array(data["feature_means"])
        self.stds = np.array(data["feature_stds"])
        self.model = data

    def extract_features(self, filepath):
        """
        从文件中提取13项"体检指标"：
        1. 熵值        — 文件有多乱（加密/混淆=高）
        2. 大小(log)   — 文件大小取对数
        3. 是否超小     — <4KB 很可疑
        4. 节数量       — PE文件的节数
        5. 是否加壳     — UPX/VMProtect等
        6. TLS回调     — 反调试技巧
        7. 可写可执行节 — 能改又能跑的节
        8. 入口为0      — 入口异常
        9. 可疑API数   — 危险函数调用次数
        10. 可疑字符串  — virus/trojan等出现次数
        11. URL数量    — 联网下载嫌疑
        12. IP数量     — 直连IP嫌疑
        13. 无数字签名  — 正规软件都有签名
        """
        feats = {}
        try:
            size = os.path.getsize(filepath)
            with open(filepath, 'rb') as f:
                data = f.read(min(size, 5 * 1024 * 1024))

            # ===== 1. 熵值：数据混乱度 =====
            if data:
                c = Counter(data)
                feats["entropy"] = -sum((v/len(data))*math.log2(v/len(data)) for v in c.values())
            else:
                feats["entropy"] = 0

            # ===== 2-3. 文件大小 =====
            feats["size_log"] = math.log2(size + 1)
            feats["small"] = 1.0 if size < 4096 else 0.0

            # ===== 4-10. PE结构分析 =====
            try:
                import pefile
                pe = pefile.PE(data=data)

                # 节数量
                feats["sections"] = pe.FILE_HEADER.NumberOfSections

                # 加壳检测：遍历所有节名
                has_packer = 0
                packers = ['.vmp', '.upx', '.aspack', '.themida', '.enigma']
                for sec in pe.sections:
                    sn = sec.Name.decode('utf-8', errors='ignore').strip('\x00').lower()
                    if any(p in sn for p in packers):
                        has_packer = 1
                        break
                feats["packer"] = float(has_packer)

                # TLS回调（恶意软件爱用来反调试）
                feats["tls"] = 0.0
                if hasattr(pe, 'DIRECTORY_ENTRY_TLS'):
                    try:
                        if pe.DIRECTORY_ENTRY_TLS.struct.AddressOfCallBacks:
                            feats["tls"] = 1.0
                    except:
                        pass

                # 可写可执行节数量
                feats["rwx"] = float(sum(1 for s in pe.sections
                                        if s.Characteristics & 0xE0000020))

                # 入口点为0
                feats["ep_zero"] = 0.0
                if hasattr(pe, 'OPTIONAL_HEADER'):
                    if pe.OPTIONAL_HEADER.AddressOfEntryPoint == 0:
                        feats["ep_zero"] = 1.0

                # 可疑API计数
                bad_apis = [b'CreateRemoteThread', b'WriteProcessMemory',
                           b'VirtualAllocEx', b'SetWindowsHookEx', b'URLDownloadToFile']
                bad_count = 0
                if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
                    for entry in pe.DIRECTORY_ENTRY_IMPORT:
                        for imp in entry.imports:
                            if imp.name in bad_apis:
                                bad_count += 1
                feats["bad_imports"] = float(bad_count)
                pe.close()
            except:
                for k in ["sections", "packer", "tls", "rwx", "ep_zero", "bad_imports"]:
                    feats.setdefault(k, 0.0)

            # ===== 11-13. 字符串特征 =====
            try:
                text = data.decode('latin-1', errors='ignore')
                import re
                # 可疑字符串出现次数（最多计50）
                count = 0
                for p in ['virus', 'trojan', 'malware', 'ransom']:
                    count += len(re.findall(p, text, re.IGNORECASE))
                feats["str_suspicious"] = min(float(count), 50)

                feats["urls"] = float(len(re.findall(r'https?://', text)))
                feats["ips"] = float(len(re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', text)))
            except:
                feats["str_suspicious"] = 0.0
                feats["urls"] = 0.0
                feats["ips"] = 0.0

        except:
            pass
        return feats

    def _tree_predict(self, tree, x):
        """
        单棵树推理：从根节点往下走
        类似"是/否"问答，最终到达叶子节点得出判断
        """
        node = 0
        while tree["children_left"][node] != -1:
            feat = tree["feature"][node]
            if feat < 0:
                break
            if x[feat] <= tree["threshold"][node]:
                node = tree["children_left"][node]   # 走左边
            else:
                node = tree["children_right"][node]  # 走右边
        val = tree["value"][node][0]
        return val[1] / sum(val) if sum(val) > 0 else 0.5

    def predict(self, filepath):
        """
        预测：这个文件是病毒吗？
        返回 (分数0~100, 特征字典)
        """
        features = self.extract_features(filepath)
        if not features:
            return 0.0, {}

        # === 有训练好的模型：100棵树投票 ===
        if self.model and self.feature_names:
            try:
                x = np.array([features.get(n, 0.0) for n in self.feature_names])
                if self.stds.sum() > 0:
                    x = (x - self.means) / (self.stds + 1e-8)

                votes = []
                for tree in self.model["trees"]:
                    votes.append(self._tree_predict(tree, x))

                score = np.mean(votes) * 100  # 0~100
                return round(float(score), 1), features
            except:
                pass

        # === 没有模型：经验公式兜底 ===
        weights = {
            "entropy": 8, "size_log": 1, "small": 10,
            "sections": 5, "packer": 25, "tls": 15,
            "rwx": 12, "ep_zero": 20, "bad_imports": 8,
            "str_suspicious": 6, "urls": 10, "ips": 12,
        }
        raw = sum(features.get(k, 0) * w for k, w in weights.items())
        score = 100 / (1 + math.exp(-raw / 50))  # Sigmoid压缩到0~100
        return round(float(score), 1), features

    def auto_train(self, malware_dir, benign_dir=None, save_path=None):
        """
        自动训练：
        1. 扫病毒文件夹 → 提取特征
        2. 扫正常文件(System32) → 提取特征
        3. 训练100棵决策树
        4. 保存模型
        """
        try:
            from sklearn.ensemble import RandomForestClassifier
            import pandas as pd
        except ImportError:
            return False, "请先安装: pip install scikit-learn pandas"

        if benign_dir is None:
            benign_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32")

        # 提取病毒特征（最多2000个）
        X_mal = []
        for root, dirs, files in os.walk(malware_dir):
            for fn in files:
                feats = self.extract_features(os.path.join(root, fn))
                if feats:
                    X_mal.append(feats)
                if len(X_mal) >= 2000:
                    break
        print(f"病毒样本: {len(X_mal)}")

        # 提取正常文件特征（最多2000个）
        X_ben = []
        for root, dirs, files in os.walk(benign_dir):
            for fn in files:
                feats = self.extract_features(os.path.join(root, fn))
                if feats:
                    X_ben.append(feats)
                if len(X_ben) >= 2000:
                    break
        print(f"正常样本: {len(X_ben)}")

        if len(X_mal) < 10 or len(X_ben) < 10:
            return False, f"样本不够 (病毒:{len(X_mal)}, 正常:{len(X_ben)})"

        # 训练！
        df_mal = pd.DataFrame(X_mal); df_mal["label"] = 1  # 1=病毒
        df_ben = pd.DataFrame(X_ben); df_ben["label"] = 0  # 0=正常
        df = pd.concat([df_mal, df_ben], ignore_index=True).fillna(0)

        feature_cols = [c for c in df.columns if c != "label"]
        X = df[feature_cols].values
        y = df["label"].values

        # 100棵树，每棵问10个问题
        model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        model.fit(X, y)

        # 导出模型
        model_data = {
            "feature_names": feature_cols,
            "feature_means": X.mean(axis=0).tolist(),
            "feature_stds": X.std(axis=0).tolist(),
            "trees": []
        }
        for tree in model.estimators_:
            model_data["trees"].append({
                "children_left": tree.tree_.children_left.tolist(),
                "children_right": tree.tree_.children_right.tolist(),
                "feature": tree.tree_.feature.tolist(),
                "threshold": tree.tree_.threshold.tolist(),
                "value": tree.tree_.value.tolist(),
            })

        if save_path is None:
            save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "resources", "ml_model.json")
            save_path = os.path.normpath(save_path)

        with open(save_path, 'w') as f:
            json.dump(model_data, f)

        self.load_model(save_path)
        return True, f"训练完成！准确率: {model.score(X, y):.1%}"
