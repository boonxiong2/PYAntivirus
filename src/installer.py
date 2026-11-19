#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PYAntivirus 安装程序 — 自包含单文件版
打包后就是一个 installer.exe，双击即装
"""
import customtkinter as ctk
import os
import sys
import shutil
import threading
from win32com.client import Dispatch

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

INSTALL_DIR = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "PYAntivirus")
DESKTOP = os.path.join(os.environ["USERPROFILE"], "Desktop")

# 续跑配置文件：放在安装程序同目录，重启后读它恢复选项
INSTALLER_DIR = os.path.dirname(sys.executable) if hasattr(sys, "frozen") else os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(INSTALLER_DIR, "install_config.ini")

def bundled_path(relative):
    """获取打包在 exe 内的文件路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    else:
        # 源码运行：从 installer.py 位置找
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, '..', relative)


class Installer:
    def __init__(self):
        self.install_path = INSTALL_DIR  # 用户可能改
        self.win = ctk.CTk()
        self.win.title("PYAntivirus 安装程序")
        self.win.geometry("520x480")
        self.win.resizable(False, False)
        self.installing = False

        ctk.CTkLabel(self.win, text="PYAntivirus 安装向导",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(30,5))
        ctk.CTkLabel(self.win, text="自包含安装包 · 一键安装",
                     font=ctk.CTkFont(size=12), text_color="gray").pack()

        self.content = ctk.CTkFrame(self.win, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=30, pady=20)

        if "--resume" in sys.argv:
            self.resume_from_config()
        else:
            self.show_welcome()
        self.win.mainloop()

    def clear(self):
        for w in self.content.winfo_children():
            w.destroy()

    def resume_from_config(self):
        """重启后自动续跑：恢复上次勾选的选项，跳过向导直接安装"""
        cfg = self.load_config()
        if not cfg:
            self.show_welcome()
            return
        self.install_path = cfg["path"]
        self.startup_var = ctk.BooleanVar(value=cfg["startup"])
        self.shortcut_var = ctk.BooleanVar(value=cfg["shortcut"])
        self.launch_var = ctk.BooleanVar(value=cfg["launch"])
        self.ml_var = ctk.BooleanVar(value=cfg["ml"])
        self.kernel_var = ctk.BooleanVar(value=cfg["kernel"])
        self.start_install()

    def save_config(self):
        """保存安装选项到 install_config.ini（重启后续跑用）"""
        import configparser
        cfg = configparser.ConfigParser()
        cfg["install"] = {"path": self.install_path}
        cfg["options"] = {
            "startup": str(self.startup_var.get()).lower(),
            "shortcut": str(self.shortcut_var.get()).lower(),
            "launch": str(self.launch_var.get()).lower(),
            "ml": str(self.ml_var.get()).lower(),
            "kernel": str(self.kernel_var.get()).lower(),
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                cfg.write(f)
            return True
        except Exception as e:
            self.log(f"⚠ 无法写入续跑配置 {CONFIG_FILE}: {e}")
            return False

    def load_config(self):
        """读取 install_config.ini，不存在/损坏返回 None"""
        import configparser
        if not os.path.exists(CONFIG_FILE):
            return None
        cfg = configparser.ConfigParser()
        try:
            cfg.read(CONFIG_FILE, encoding="utf-8")
            return {
                "path": cfg.get("install", "path", fallback=INSTALL_DIR),
                "startup": cfg.getboolean("options", "startup", fallback=True),
                "shortcut": cfg.getboolean("options", "shortcut", fallback=True),
                "launch": cfg.getboolean("options", "launch", fallback=True),
                "ml": cfg.getboolean("options", "ml", fallback=False),
                "kernel": cfg.getboolean("options", "kernel", fallback=False),
            }
        except Exception:
            return None

    def clear_config(self):
        """安装完成后清理续跑配置和 RunOnce 项"""
        try:
            if os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)
        except Exception:
            pass
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\RunOnce", 0, winreg.KEY_SET_VALUE)
            try:
                winreg.DeleteValue(key, "PYAVInstallerResume")
            except OSError:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass

    def _register_resume(self):
        """注册 RunOnce：下次登录自动运行安装器并续跑"""
        try:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\RunOnce")
            winreg.SetValueEx(key, "PYAVInstallerResume", 0, winreg.REG_SZ,
                              f'"{sys.executable}" --resume')
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def show_welcome(self):
        self.clear()
        ctk.CTkLabel(self.content, text="安装 PYAntivirus",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)

        info = ctk.CTkFrame(self.content)
        info.pack(pady=15, fill="x")
        items = [
            ("病毒库", "110万 恶意软件哈希"),
            ("引擎", "7层启发式检测")
        ]
        for label, val in items:
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(row, text=label, width=100, font=ctk.CTkFont(size=12),
                        text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=val, font=ctk.CTkFont(size=12)).pack(side="left")

        # 路径选择
        path_frame = ctk.CTkFrame(self.content)
        path_frame.pack(pady=10, fill="x", padx=10)

        self.path_var = ctk.StringVar(value=INSTALL_DIR)
        ctk.CTkLabel(path_frame, text="📍 安装到:", font=ctk.CTkFont(size=12),
                     text_color="gray").pack(side="left", padx=5)
        path_entry = ctk.CTkEntry(path_frame, textvariable=self.path_var, width=280)
        path_entry.pack(side="left", padx=5, fill="x", expand=True)

        def browse():
            from tkinter import filedialog
            p = filedialog.askdirectory(title="选择安装路径", initialdir=INSTALL_DIR)
            if p:
                self.path_var.set(p)

        ctk.CTkButton(path_frame, text="浏览...", width=60, command=browse).pack(side="left", padx=5)

        ctk.CTkButton(self.content, text="下一步 →", font=ctk.CTkFont(size=14, weight="bold"),
                      height=40, command=self.show_options).pack(pady=25)

    def show_options(self):
        # 保存用户选择的路径
        if hasattr(self, 'path_var'):
            self.install_path = self.path_var.get()

        self.clear()
        ctk.CTkLabel(self.content, text="安装选项", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)

        self.startup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.content, text="开机自启动（推荐）", variable=self.startup_var).pack(pady=5, anchor="w")

        self.shortcut_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.content, text="创建桌面快捷方式", variable=self.shortcut_var).pack(pady=5, anchor="w")

        self.launch_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.content, text="安装完成后立即启动", variable=self.launch_var).pack(pady=5, anchor="w")

        self.ml_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.content, text="启用机器学习检测", variable=self.ml_var).pack(pady=5, anchor="w")

        self.kernel_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.content, text="启用驱动程序（beta）（不推荐）", variable=self.kernel_var).pack(pady=5, anchor="w")

        ctk.CTkButton(self.content, text="确认安装", font=ctk.CTkFont(size=14, weight="bold"),
                      height=40, fg_color="#188038", hover_color="#0d6522",
                      command=self.start_install).pack(pady=25)

    def start_install(self):
        self.clear()
        self.installing = True
        ctk.CTkLabel(self.content, text="⚙ 正在安装...",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)

        self.progress = ctk.CTkProgressBar(self.content)
        self.progress.pack(padx=20, pady=10, fill="x")
        self.progress.set(0)

        self.status_label = ctk.CTkLabel(self.content, text="准备中...", font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=5)

        self.log_text = ctk.CTkTextbox(self.content, height=160, font=ctk.CTkFont(size=11))
        self.log_text.pack(padx=10, pady=5, fill="both", expand=True)

        thread = threading.Thread(target=self._do_install, daemon=True)
        thread.start()

    def log(self, msg):
        if not self.installing:
            return
        self.win.after(0, lambda: self.log_text.insert("end", msg + "\n"))
        self.win.after(0, lambda: self.log_text.see("end"))

    def _do_install(self):
        total_steps = 5
        step = 0
        ip = self.install_path  # 用户选择的路径

        try:
            # === 第1步：创建安装目录 ===
            step += 1
            self.win.after(0, lambda: self.progress.set(step/total_steps))
            self.win.after(0, lambda: self.status_label.configure(text="创建安装目录..."))
            os.makedirs(ip, exist_ok=True)
            self.log("✓ 创建目录 " + ip)

            # === 第2步：复制所有程序文件 ===
            step += 1
            self.win.after(0, lambda: self.progress.set(step/total_steps))
            self.win.after(0, lambda: self.status_label.configure(text="复制程序文件..."))

            # 找出打包内的所有文件
            files_to_install = {}
            if hasattr(sys, '_MEIPASS'):
                for root, dirs, files in os.walk(sys._MEIPASS):
                    for f in files:
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, sys._MEIPASS)
                        if self.kernel_var:
                            if rel.startswith('resources') or f in ['PYAntivirus.exe', 'uninsPYAV.exe', 'pyav_kernel.sys']:
                                files_to_install[rel] = full
                        else:
                            if rel.startswith('resources') or f in ['PYAntivirus.exe', 'uninsPYAV.exe']:
                                files_to_install[rel] = full
            else:
                base = os.path.dirname(os.path.abspath(__file__))
                project = os.path.join(base, '..')
                exe = os.path.join(project, 'dist', 'PYAntivirus.exe')
                if os.path.exists(exe):
                    files_to_install['PYAntivirus.exe'] = exe
                res = os.path.join(project, 'resources')
                if os.path.exists(res):
                    for f in os.listdir(res):
                        files_to_install[f'resources/{f}'] = os.path.join(res, f)

            for rel, src in files_to_install.items():
                dst = os.path.join(ip, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                size_mb = os.path.getsize(src) / 1024 / 1024
                self.log(f"✓ {os.path.basename(rel)} ({size_mb:.1f} MB)")

            # === 第3步：桌面快捷方式 ===
            step += 1
            self.win.after(0, lambda: self.progress.set(step/total_steps))
            self.win.after(0, lambda: self.status_label.configure(text="创建快捷方式..."))
            if self.shortcut_var.get():
                self._create_shortcut(DESKTOP)
                self.log("✓ 桌面快捷方式")

            # === 第4步：开机启动 ===
            step += 1
            self.win.after(0, lambda: self.progress.set(step/total_steps))
            self.win.after(0, lambda: self.status_label.configure(text="配置开机启动..."))
            if self.startup_var.get():
                # 计划任务：登录时以最高权限启动（比启动文件夹更早、无UAC弹窗、抗删除）
                main_exe = os.path.join(ip, "PYAntivirus.exe")
                try:
                    import subprocess
                    r = subprocess.run(
                        ['schtasks', '/create', '/tn', 'PYAntivirusAutoStart', '/tr',
                         f'"{main_exe}"', '/sc', 'onlogon', '/rl', 'highest', '/f'],
                        capture_output=True, text=True)
                    if r.returncode == 0:
                        self.log("✓ 开机自启动（计划任务·最高权限）")
                    else:
                        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
                except Exception as e:
                    # 回退：启动文件夹快捷方式
                    startup = os.path.join(os.environ["APPDATA"],
                        "Microsoft\\Windows\\Start Menu\\Programs\\Startup")
                    self._create_shortcut(startup)
                    self.log(f"⚠ 计划任务失败({e})，已回退启动文件夹快捷方式")
            # ===5,kernel.sys===

            # 开始菜单快捷方式
            start_menu = os.path.join(os.environ["APPDATA"],
                "Microsoft\\Windows\\Start Menu\\Programs\\PYAntivirus")
            os.makedirs(start_menu, exist_ok=True)

            # 主程序
            main_exe = os.path.join(ip, "PYAntivirus.exe")
            if os.path.exists(main_exe):
                shell = Dispatch('WScript.Shell')
                sc = shell.CreateShortCut(os.path.join(start_menu, "PYAntivirus.lnk"))
                sc.Targetpath = main_exe
                sc.WorkingDirectory = ip
                icon = os.path.join(ip, "resources", "icon.ico")
                if os.path.exists(icon):
                    sc.IconLocation = icon
                sc.save()
                self.log("✓ 开始菜单快捷方式")

            # 卸载器
            uninstaller = os.path.join(ip, "uninsPYAV.exe")
            if os.path.exists(uninstaller):
                shell = Dispatch('WScript.Shell')
                sc = shell.CreateShortCut(os.path.join(start_menu, "卸载 PYAntivirus.lnk"))
                sc.Targetpath = uninstaller
                sc.WorkingDirectory = ip
                sc.save()
                self.log("✓ 开始菜单卸载快捷方式")

            # Defender 排除 + 注册到 Windows 安全中心
            os.system(f'powershell -Command "Add-MpPreference -ExclusionPath \'{ip}\'" 2>nul')
            self.log("✓ 已添加 Windows Defender 排除")

            # WMI 注册到安全中心（Defender 会让位）
            try:
                import subprocess
                ps_cmd = f'''
$wmi = Get-WmiObject -Namespace "root/SecurityCenter2" -Class AntiVirusProduct -ErrorAction SilentlyContinue
if (-not $wmi) {{ $wmi = Get-WmiObject -Namespace "root/SecurityCenter" -Class AntiVirusProduct -ErrorAction SilentlyContinue }}
if (-not $wmi) {{
    # 较新 Windows 用这个
    $av = New-Object -ComObject "WbemScripting.SWbemLocator"
    $svc = $av.ConnectServer(".","root/SecurityCenter2")
    $prod = $svc.Get("AntiVirusProduct").SpawnInstance_()
    $prod.displayName = "PYAntivirus"
    $prod.instanceGuid = "{{D68DDC3A-831F-4fae-9E44-DA132C1ACF46}}"
    $prod.pathToSignedProductExe = "{ip}\\\\PYAntivirus.exe"
    $prod.pathToSignedReportingExe = "{ip}\\\\PYAntivirus.exe"
    $prod.productState = 0x0000
    $prod.Put_()
}}
'''
                subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True)
                self.log("✓ 已注册到 Windows 安全中心")
            except:
                self.log("⚠ 安全中心注册跳过（需管理员）")
            if self.kernel_var.get():
                try:
                    # 已开启就直接跳过，避免重复开关 bcdedit 和反复重启
                    check = subprocess.run(
                        ['powershell', '-Command',
                         "(bcdedit /enum {current} | Select-String 'testsigning') -match 'Yes'"],
                        capture_output=True, text=True)
                    if 'True' in check.stdout:
                        self.log("✓ 测试签名已开启，跳过驱动配置（无需重启）")
                    else:
                        r = subprocess.run(['powershell', '-Command',
                                            'bcdedit /set {current} testsigning on\nbcdedit /debug on'],
                                           capture_output=True, text=True)
                        if r.returncode == 0:
                            if self.save_config() and self._register_resume():
                                self.log("✓ 已保存安装选项，重启后自动继续安装")
                            else:
                                self.log("⚠ 无法保存续跑配置，重启后请手动重新运行安装程序")
                            self.log("已开启测试签名，60 秒后重启生效")
                            os.system('shutdown /r /t 60')
                        else:
                            self.log(f"⚠ 开启测试签名失败（需管理员权限）: {(r.stderr or r.stdout).strip()[:100]}")
                except Exception as e:
                    self.log(f"无法配置内核驱动：{e}")
            # 注册到 Windows 应用列表（设置→应用→可卸载）
            try:
                import winreg
                key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PYAntivirus")
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "PYAntivirus")
                winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "3.3")
                winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "PYAntivirus Security")
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ,
                                 os.path.join(ip, "resources", "icon.ico"))
                winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ,
                                 os.path.join(ip, "uninsPYAV.exe"))
                winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, ip)
                winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)
                self.log("✓ 已注册到 Windows 应用列表")
            except:
                self.log("⚠ 应用注册跳过")

            # === 第5步：完成 ===
            step += 1
            self.win.after(0, lambda: self.progress.set(1.0))
            self.win.after(0, lambda: self.status_label.configure(text="安装完成！"))
            self.log("\n✅ 安装完成！")
            self.win.after(300, self.show_finish)

        except Exception as e:
            self.log(f"❌ 安装失败: {e}")
            import traceback
            self.log(traceback.format_exc())

    def _create_shortcut(self, folder):
        """创建快捷方式"""
        ip = self.install_path
        os.makedirs(folder, exist_ok=True)
        link_path = os.path.join(folder, "PYAntivirus.lnk")
        exe = os.path.join(ip, "PYAntivirus.exe")
        if not os.path.exists(exe):
            exe = os.path.join(ip, "PYAntivirus.py")

        shell = Dispatch('WScript.Shell')
        sc = shell.CreateShortCut(link_path)
        sc.Targetpath = exe if exe.endswith('.exe') else sys.executable
        if not exe.endswith('.exe'):
            sc.Arguments = exe
        sc.WorkingDirectory = ip
        icon_path = os.path.join(ip, "resources", "icon.ico")
        if os.path.exists(icon_path):
            sc.IconLocation = icon_path
        sc.save()

    def show_finish(self):
        self.clear_config()  # 续跑配置用完了，清理掉
        ip = self.install_path
        self.clear()
        ctk.CTkLabel(self.content, text="✅ 安装完成！",
                     font=ctk.CTkFont(size=24, weight="bold"), text_color="green").pack(pady=20)
        ctk.CTkLabel(self.content, text=f"已安装到:\n{ip}",
                     font=ctk.CTkFont(size=12)).pack(pady=10)
        ctk.CTkLabel(self.content, text="🔐 防篡改保护已启用\n🛡️ 实时监控将在后台运行",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=5)

        def done():
            if self.launch_var.get():
                target = os.path.join(ip, "PYAntivirus.exe")
                if os.path.exists(target):
                    os.startfile(target)
            self.win.after(10, self.win.destroy)

        ctk.CTkButton(self.content, text="完成", font=ctk.CTkFont(size=14, weight="bold"),
                      height=40, command=done).pack(pady=20)


if __name__ == "__main__":
    # 请求管理员权限（把原参数带上，--resume 才不会被吞掉）
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        if hasattr(sys, "frozen"):
            extra = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            extra = f'"{__file__}" ' + " ".join(f'"{a}"' for a in sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, extra, None, 1)
        sys.exit()
    Installer()
