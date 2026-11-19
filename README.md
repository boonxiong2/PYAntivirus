# PYAntivirus

Windows 杀毒软件 —— Python (customtkinter GUI) + C 内核驱动（WDK）。

多层检测引擎 + Ring0 进程保护 + 活的病毒库。

## 架构

```
┌─ 用户态 (Python) ────────────────────────────────────────┐
│  PYAntivirus.py      主程序：GUI、扫描引擎、文件监控、自保护 │
│  AtivirusKernelIO.py 驱动通信客户端（IOCTL）              │
│  ml_scanner.py       13 特征随机森林（JSON 树，推理零依赖）│
│  pyav_client.py      独立 IOCTL 客户端 / 命令行            │
│  installer.py        安装器（计划任务自启动、重启续跑）    │
│  uninstaller.py      卸载器                               │
│  Cmd_Antivirus.py    老版命令行（已归档）                  │
│  CommandAntivirus-纪念版.py  新引擎 + 纯命令行（无 GUI 依赖）│
├─ 内核态 (C, WDK) ────────────────────────────────────────┤
│  kernel.c            pyav_kernel.sys                      │
│                      · 进程创建/退出回调                   │
│                      · 受保护进程表                        │
│                      · ObRegisterCallbacks 句柄剥离        │
│                      · 注册表回调                          │
│                      · IOCTL: 版本/保护/杀进程/PID 扫描    │
└──────────────────────────────────────────────────────────┘
```

## 检测层（5 层）

| 层 | 说明 |
|---|---|
| 1. 哈希匹配 | MD5 库（`resources/virus_hash_lib.txt`），txt 极速加载 + 损坏自动回退 JSON |
| 2. 启发式 | PE 深度分析、熵值、可疑 API/字符串、加壳检测、反虚拟机、勒索行为 |
| 3. YARA 规则 | 数据驱动：`resources/yara_rules.json`（家族特征：银狐/WannaCry/挖矿/Gh0st…） |
| 4. 机器学习 | 13 维特征 + 随机森林（推理纯 Python，不依赖 sklearn）|
| 5. Ring0 | 内核 PID 空间扫描发现**隐藏进程**（摘链也逃不掉）+ 句柄剥离防杀 |

## Ring0 能力

- **隐藏进程检测**：内核遍历 PID 空间（`PsLookupProcessByProcessId`），与用户态 `psutil` 列表对比 → 差值即隐藏进程。不硬编码 EPROCESS 偏移，无版本蓝屏风险。
- **防杀**：`ObRegisterCallbacks` 预回调剥掉 `PROCESS_TERMINATE`/`VM_WRITE` 等权限位。
- **内核杀进程**：`ZwOpenProcess` + `ZwTerminateProcess`（优先于用户态 `psutil`）。

## 构建

需要 MSVC + WDK 10（驱动）与 Python 3.11（主程序）。

```bat
make.bat
```

产出：`dist\PYAntivirus.exe`、`dist\uninsPYAV.exe`、`dist\PYAntivirus_Installer.exe`、`dist\packages\ml_trainer.exe`（独立 ML 训练器）。

驱动单独构建：

```bat
call "D:\VS26\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
cmake --build out\build\x64-Debug
```

## 病毒库

仓库**不包含**病毒库（体积过大）。首次使用前生成：

```powershell
# API key: https://mb-api.abuse.ch 免费，存到 ~/.mb_api_key
python tools\update_virus_db.py
```

多源更新（MalwareBazaar 近 60 分钟 + 40 个家族定向 + 近 7 天检出样本），带节流、429 退避、原子写入、last-known-good 回滚。

## 工具

| 脚本 | 用途 |
|---|---|
| `tools/update_virus_db.py` | 拉取病毒库（多源）|
| `tools/submit_sample.py` | 匿名提交样本到 MalwareBazaar（仅限确认的恶意软件）|
| `tools/gen_integrity.py` | 生成 `integrity.json` 自保护清单（打包前必跑）|
| `src/train_model.py` | ML 模型训练（打包为 `ml_trainer.exe`）|

## 自保护

启动时校验 `resources/integrity.json` 中关键资源的 SHA256 前缀；清单在打包时由 `tools/gen_integrity.py` 生成（`make.bat` 第 0 步自动调用）。

> 病毒库更新后需重新生成清单，否则会误报"文件被篡改"。

## 免责声明

仅用于学习与自有环境防护。内核驱动需要测试签名模式（`bcdedit /set testsigning on`），请勿在未授权的环境中加载。
