"""
PYAntivirus ML 模型训练（独立脚本）
需要: pip install scikit-learn pandas
"""
import os, sys, json, math, hashlib
from collections import Counter
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--malware", required=True, help="病毒样本文件夹")
parser.add_argument("--benign", required=True, help="正常文件文件夹")
parser.add_argument("--output", default="ml_model.json")
parser.add_argument("--use-lightgbm", action="store_true", help="使用LightGBM(更快更准)")
args = parser.parse_args()

# 复用 MLScanner 的特征提取（避免重复代码）
from ml_scanner import MLScanner
scanner = MLScanner()
extract_features = scanner.extract_features


print("Extracting malware features...")
X_mal = []
for root, dirs, files in os.walk(args.malware):
    for fn in files:
        fp = os.path.join(root, fn)
        feats = extract_features(fp)
        if feats:
            X_mal.append(feats)
        if len(X_mal) % 500 == 0:
            print(f"\r  {len(X_mal)} malware samples...", end="")

print(f"\r  {len(X_mal)} malware samples")

print("Extracting benign features...")
X_ben = []
for root, dirs, files in os.walk(args.benign):
    for fn in files:
        fp = os.path.join(root, fn)
        feats = extract_features(fp)
        if feats:
            X_ben.append(feats)
        if len(X_ben) % 500 == 0:
            print(f"\r  {len(X_ben)} benign samples...", end="")

print(f"\r  {len(X_ben)} benign samples")

# 训练 RandomForest
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

df_mal = pd.DataFrame(X_mal); df_mal["label"] = 1
df_ben = pd.DataFrame(X_ben); df_ben["label"] = 0
df = pd.concat([df_mal, df_ben], ignore_index=True).fillna(0)

feature_cols = [c for c in df.columns if c != "label"]
X = df[feature_cols].values
y = df["label"].values

# 类别平衡检查
n_mal, n_ben = int(y.sum()), len(y) - int(y.sum())
print(f"病毒: {n_mal}  正常: {n_ben}")
if abs(n_mal - n_ben) > max(n_mal, n_ben) * 0.5:
    print("⚠ 样本不平衡，建议增加较少类别的样本")

# 交叉验证
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.ensemble import RandomForestClassifier

# LightGBM 可选
if args.use_lightgbm:
    try:
        from lightgbm import LGBMClassifier
        model = LGBMClassifier(n_estimators=100, max_depth=10, random_state=42, verbose=-1)
        print("使用 LightGBM")
    except ImportError:
        print("LightGBM未安装，退回随机森林")
        model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
else:
    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)

# K折交叉验证
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
scores = cross_val_score(model, X, y, cv=cv, scoring='accuracy')
print(f"5折交叉验证: {scores.mean():.2%} (±{scores.std():.2%})")

# 最终训练
model.fit(X, y)
print(f"训练集准确率: {model.score(X, y):.2%}")

# 导出模型
model_data = {
    "feature_names": feature_cols,
    "feature_means": X.mean(axis=0).tolist(),
    "feature_stds": X.std(axis=0).tolist(),
    "n_estimators": len(model.estimators_),
    "trees": []
}

for tree in model.estimators_:
    tree_data = {
        "children_left": tree.tree_.children_left.tolist(),
        "children_right": tree.tree_.children_right.tolist(),
        "feature": tree.tree_.feature.tolist(),
        "threshold": tree.tree_.threshold.tolist(),
        "value": tree.tree_.value.tolist(),
    }
    model_data["trees"].append(tree_data)

with open(args.output, 'w') as f:
    json.dump(model_data, f)

size_mb = os.path.getsize(args.output) / 1024 / 1024
print(f"Model saved: {args.output} ({size_mb:.1f} MB)")

# 把模型路径写进注册表，主程序启动时直接读这里
try:
    import winreg
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\PYAntivirus")
    winreg.SetValueEx(key, "MLModelPath", 0, winreg.REG_SZ, os.path.abspath(args.output))
    winreg.CloseKey(key)
    print(f"✓ 已注册模型路径: HKCU\\Software\\PYAntivirus\\MLModelPath = {os.path.abspath(args.output)}")
except Exception as e:
    print(f"⚠ 注册表写入失败（不影响训练结果，主程序会退化到 exe 旁查找）: {e}")

print("Copy to resources/ folder to enable ML detection!")
