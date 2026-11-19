#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PYAntivirus 卸载程序 - 图形界面版"""
import os, sys, shutil, ctypes, threading
import customtkinter as ctk

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

# 获取真实安装目录（兼容 pyinstaller 打包）
if hasattr(sys, '_MEIPASS'):
    # pyinstaller 打包：用 exe 所在目录
    INSTALL_DIR = os.path.dirname(sys.executable)
else:
    INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))

# 如果当前路径不像安装目录，去 Program Files 找
if not os.path.exists(os.path.join(INSTALL_DIR, "PYAntivirus.exe")):
    for alt_base in [os.environ.get("ProgramFiles", "C:\\Program Files"),
                     os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                     os.environ.get("LOCALAPPDATA", "")]:
        alt = os.path.join(alt_base, "PYAntivirus")
        if os.path.exists(os.path.join(alt, "PYAntivirus.exe")):
            INSTALL_DIR = alt
            break


class Uninstaller:
    def __init__(self):
        self.win = ctk.CTk()
        self.win.title("PYAntivirus 卸载")
        self.win.geometry("420x380")
        self.win.resizable(False, False)

        # 确认页
        self.content = ctk.CTkFrame(self.win, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=30, pady=20)

        ctk.CTkLabel(self.content, text="🗑 卸载 PYAntivirus",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=15)

        warning = ctk.CTkFrame(self.content, fg_color="#b71c1c", corner_radius=8)
        warning.pack(pady=10, fill="x")
        ctk.CTkLabel(warning, text="⚠ 此操作将删除所有程序文件！\n病毒库、设置、防护将全部移除。",
                     font=ctk.CTkFont(size=12), text_color="white").pack(pady=12, padx=15)

        ctk.CTkLabel(self.content, text=f"安装路径:\n{INSTALL_DIR}",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=5)

        ctk.CTkLabel(self.content, text="确定要卸载吗？",
                     font=ctk.CTkFont(size=14)).pack(pady=10)

        btn_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="确认卸载", fg_color="#d93025", hover_color="#b71c1c",
                      width=120, height=40, command=self.start_uninstall).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="取消", fg_color="gray", width=120, height=40,
                      command=self.win.destroy).pack(side="left", padx=10)

        # 进度区（初始隐藏）
        self.progress_frame = ctk.CTkFrame(self.win, fg_color="transparent")

        self.win.mainloop()

    def start_uninstall(self):
        # 切换到进度界面
        self.content.pack_forget()
        self.progress_frame.pack(fill="both", expand=True, padx=30, pady=20)

        ctk.CTkLabel(self.progress_frame, text="⚙ 正在卸载...",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=15)

        self.progress = ctk.CTkProgressBar(self.progress_frame)
        self.progress.pack(padx=10, pady=10, fill="x")
        self.progress.set(0)

        self.status = ctk.CTkLabel(self.progress_frame, text="准备中...",
                                    font=ctk.CTkFont(size=12))
        self.status.pack(pady=5)

        self.log = ctk.CTkTextbox(self.progress_frame, height=120, font=ctk.CTkFont(size=11))
        self.log.pack(padx=5, pady=5, fill="both", expand=True)

        thread = threading.Thread(target=self._do_uninstall, daemon=True)
        thread.start()

    def _log(self, msg):
        self.win.after(0, lambda: self.log.insert("end", msg + "\n"))
        self.win.after(0, lambda: self.log.see("end"))

    def _do_uninstall(self):
        try:
            # 1. 杀进程
            self.win.after(0, lambda: self.status.configure(text="停止 PYAntivirus..."))
            self.win.after(0, lambda: self.progress.set(0.25))
            os.system('taskkill /f /im PYAntivirus.exe 2>nul')
            os.system('taskkill /f /im "Command antivirus.exe" 2>nul')
            self._log("✓ 已停止进程")

            # 2. 注销安全中心 + 清理注册表
            os.system(f'powershell -Command "Remove-MpPreference -ExclusionPath \'{INSTALL_DIR}\'" 2>nul')
            os.system('powershell -Command "Get-WmiObject -Namespace root/SecurityCenter2 -Class AntiVirusProduct | Where-Object {$_.displayName -eq \'PYAntivirus\'} | Remove-WmiObject" 2>nul')
            try:
                import winreg
                winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PYAntivirus")
            except:
                pass
            self._log("✓ 注销安全中心 + 清理注册表")

            # 3. 删快捷方式
            self.win.after(0, lambda: self.status.configure(text="删除快捷方式..."))
            self.win.after(0, lambda: self.progress.set(0.5))
            desktop = os.path.join(os.environ["USERPROFILE"], "Desktop", "PYAntivirus.lnk")
            startup = os.path.join(os.environ["APPDATA"],
                r"Microsoft\Windows\Start Menu\Programs\Startup\PYAntivirus.lnk")
            start_menu = os.path.join(os.environ["APPDATA"],
                r"Microsoft\Windows\Start Menu\Programs\PYAntivirus")
            for f in [desktop, startup]:
                if os.path.exists(f):
                    os.remove(f)
                    self._log(f"✓ 删除: {os.path.basename(f)}")
            # 删开机自启动计划任务
            try:
                import subprocess
                subprocess.run(['schtasks', '/delete', '/tn', 'PYAntivirusAutoStart', '/f'],
                               capture_output=True)
                self._log("✓ 已删除开机自启动计划任务")
            except Exception:
                pass
            if os.path.exists(start_menu):
                shutil.rmtree(start_menu, ignore_errors=True)
                self._log("✓ 删除开始菜单")

            # 4. 删程序目录（用强力批处理）
            self.win.after(0, lambda: self.status.configure(text="删除程序文件..."))
            self.win.after(0, lambda: self.progress.set(0.75))
            tmp = os.path.join(os.environ["TEMP"], "pyav_del.bat")
            with open(tmp, 'w') as f:
                f.write(f'''@echo off
timeout /t 2 /nobreak >nul
:retry
rmdir /s /q "{INSTALL_DIR}" 2>nul
if exist "{INSTALL_DIR}" (
    takeown /f "{INSTALL_DIR}" /r /d y >nul 2>&1
    icacls "{INSTALL_DIR}" /grant Everyone:F /t /q >nul 2>&1
    rmdir /s /q "{INSTALL_DIR}" 2>nul
)
del "%~f0"
''')
            os.system(f'start "" cmd /c "{tmp}"')
            self._log("✓ 程序文件已排程删除")

            # 4. 完成
            self.win.after(0, lambda: self.progress.set(1.0))
            self.win.after(0, lambda: self.status.configure(text="卸载完成！"))
            self._log("\n✅ PYAntivirus 已卸载")

            self.win.after(1500, self.show_done)

        except Exception as e:
            self._log(f"❌ 错误: {e}")

    def show_done(self):
        self.progress_frame.pack_forget()
        done_frame = ctk.CTkFrame(self.win, fg_color="transparent")
        done_frame.pack(fill="both", expand=True, padx=30, pady=20)

        ctk.CTkLabel(done_frame, text="✅ 卸载完成",
                     font=ctk.CTkFont(size=22, weight="bold"), text_color="green").pack(pady=20)
        ctk.CTkLabel(done_frame, text="PYAntivirus 已从您的计算机移除。",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=5)

        ctk.CTkButton(done_frame, text="关闭", command=self.win.destroy,
                      width=100, height=35).pack(pady=20)


if __name__ == "__main__":
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, __file__, None, 1)
        sys.exit()
    Uninstaller()
