# ==================== 导入库 ====================
import customtkinter as ctk

from tkinter import filedialog
import pystray
from PIL import Image, ImageDraw
import sys
import os
import time
import hashlib
import argparse
import json
import re
import pefile
import string
from datetime import datetime

from win32api import GetCurrentProcess
from windows_toasts import Toast, WindowsToaster
from collections import Counter
import math
import struct
import binascii
import psutil
import ctypes
import threading
import queue
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ctypes import wintypes

# ==================== 资源路径（兼容 EXE 和源码运行）====================
def resource_path(relative_path):
    """获取资源文件路径，兼容 pyinstaller 打包和源码运行"""
    if hasattr(sys, '_MEIPASS'):
        # pyinstaller 打包后
        base = sys._MEIPASS
    else:
        # 源码运行：从 src/ 往上一级找 resources/
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resources')
    return os.path.join(base, relative_path)


def ml_model_path():
    """ML模型路径优先级：注册表(训练器写入) → exe旁(打包训练) → 嵌入/项目资源"""
    cands = []
    # 1. 注册表：ml_trainer.exe 训练完写入的模型路径
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\PYAntivirus")
        try:
            reg_path, _ = winreg.QueryValueEx(key, "MLModelPath")
            if reg_path:
                cands.append(reg_path)
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass
    # 2. exe 旁（打包后训练结果持久化）→ 嵌入资源（默认模型）
    if hasattr(sys, '_MEIPASS'):
        cands += [
            os.path.join(os.path.dirname(sys.executable), "ml_model.json"),
            os.path.join(sys._MEIPASS, "ml_model.json"),
        ]
    else:
        # 源码跑：项目 resources/（与 auto_train 默认保存位置一致）
        cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resources', "ml_model.json"))
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]

_main_ = 1
started_ui_mode = 0
main_window = 0
kernel32 = ctypes.WinDLL('kernel32.dll')
TerminateProcess = kernel32.TerminateProcess
GetCurrentProcess = kernel32.GetCurrentProcess

toaster = WindowsToaster("Antivirus")

# ==================== 全局配置 ====================
ctk.set_appearance_mode("system")         # 跟随系统主题
ctk.set_default_color_theme("blue")      # 蓝色主题

# 原生 Windows 弹窗
import tkinter.messagebox as mb
def msg_info(title, message): mb.showinfo(title, message)
def msg_warn(title, message): mb.showwarning(title, message)
def msg_error(title, message): mb.showerror(title, message)
def msg_ask(title, message): return mb.askyesno(title, message)

from ml_scanner import MLScanner

# ==================== 托盘管理器（原样保留）====================
class SystemTrayManager:
    """系统托盘管理器，用于后台运行"""

    def __init__(self, antivirus_instance, monitor_paths=None):
        self.av = antivirus_instance
        self.monitor_paths = monitor_paths or []
        self.tray_icon = None
        self.monitoring = False
        self.monitor_thread = None
        self.monitor_handler = None

    def create_tray_icon(self):
        try:
            image = Image.open(resource_path("icon.ico"))
            if image.size[0] > 64 or image.size[1] > 64:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)
        except FileNotFoundError:
            print("[!] 找不到icon.ico文件，使用默认图标")
            image = self._create_default_icon()
        except Exception as e:
            print(f"[!] 加载图标失败: {e}")
            image = self._create_default_icon()

        menu = pystray.Menu(
            pystray.MenuItem("显示主界面", self.show_main_window, default=True),
            pystray.MenuItem("扫描状态", self.show_status),
            pystray.MenuItem("暂停监控", self.toggle_monitoring),
            pystray.MenuItem("---", None, enabled=False),
            pystray.MenuItem("设置", self.open_settings),
            pystray.MenuItem("关于", self.show_about),
            pystray.MenuItem("---", None, enabled=False),
            pystray.MenuItem("退出", self.quit_program)
        )

        self.tray_icon = pystray.Icon(
            "antivirus_tray",
            image,
            "命令行杀毒软件 (后台运行中)",
            menu
        )

    def _create_default_icon(self):
        image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill=(220, 50, 50), outline=(180, 30, 30), width=3)
        draw.line([24, 32, 32, 40], fill=(255, 255, 255), width=3)
        draw.line([32, 40, 40, 32], fill=(255, 255, 255), width=3)
        return image
    def show_main_window(self, icon, item):
        """显示主界面"""
        global ui_root, main_window
        if ui_root:
            ui_root.deiconify()  # 恢复窗口
            ui_root.lift()       # 置顶
        main_window = 1

    def show_status(self, icon, item):
        status_msg = (f"扫描状态\n"
                      f"扫描文件: {self.av.stats.get('scanned', 0)}\n"
                      f"发现病毒: {self.av.stats.get('infected', 0)}\n"
                      f"可疑文件: {self.av.stats.get('suspicious', 0)}\n"
                      f"监控状态: {'运行中' if self.monitoring else '已停止'}")
        msg_info("杀毒软件状态", status_msg)

    def toggle_monitoring(self, icon, item):
        if self.monitoring:
            self.stop_monitoring()
            item.text = "启动监控"
        else:
            self.start_monitoring()
            item.text = "暂停监控"

    def open_settings(self, icon, item):
        global av_instance
        if av_instance:
            show_settings_dialog(av_instance)

    def show_about(self, icon, item):
        show_about_dialog()

    def quit_program(self, icon, item):
        global _main_
        if self.monitoring:
            self.stop_monitoring()
        if self.tray_icon:
            self.tray_icon.stop()
        _main_ = 0
        try:
            if hasattr(self, 'av') and self.av:
                self.av.save_settings()
        except:
            pass
        import os
        os._exit(0)

    def start_monitoring(self):
        if not self.monitor_paths:
            default_path = os.path.join(os.path.expanduser("~"), "Downloads")
            self.monitor_paths = [default_path]
        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._run_monitoring)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            print("[*] 后台监控已启动")

    def _run_monitoring(self):
        print(f"[*] 开始监控目录: {self.monitor_paths}")

    def stop_monitoring(self):
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("[*] 后台监控已停止")

    def run_in_tray(self):
        self.create_tray_icon()
        self.start_monitoring()
        self.tray_icon.run()


class AutoScanHandler(FileSystemEventHandler):
    """文件系统事件处理器，用于自动扫描新文件"""

    def __init__(self, antivirus_instance, scan_delay=2):
        super().__init__()
        self.av = antivirus_instance
        self.scan_delay = scan_delay
        self.file_queue = queue.Queue()
        # 单消费者线程串行扫描：避免每个事件开新线程导致线程爆炸
        worker = threading.Thread(target=self._consumer, daemon=True)
        worker.start()

    def on_created(self, event):
        if not event.is_directory:
            print(f"[监控] 检测到新文件: {event.src_path}")
            self.file_queue.put(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            print(f"[监控] 检测到文件被修改: {event.src_path}")
            self.file_queue.put(event.src_path)

    def _consumer(self):
        """队列消费者：延迟后串行扫描"""
        while True:
            file_path = self.file_queue.get()
            try:
                time.sleep(self.scan_delay)
                if not os.path.exists(file_path):
                    print(f"[监控] 文件已不存在，跳过扫描: {file_path}")
                    continue
                print(f"[监控] 开始扫描文件: {file_path}")
                scan_type, virus_hash, score, findings, file_hash = self.av.scan_file(file_path, "md5")
                if scan_type == "hash":
                    print(f"[!] 发现病毒: {file_path}")
                    self.av.stats["infected"] += 1
                    self.av.infected_files.append({
                        "path": file_path, "type": "已知病毒", "hash": virus_hash,
                        "score": score, "findings": findings
                    })
                    self._send_alert_notification(file_path, "病毒", score)
                elif scan_type == "heuristic":
                    print(f"[!] 发现可疑文件: {file_path} (评分: {score})")
                    self.av.stats["suspicious"] += 1
                    self.av.suspicious_files.append({
                        "path": file_path, "type": "可疑文件", "hash": file_hash,
                        "score": score, "findings": findings
                    })
                    self._send_alert_notification(file_path, "可疑文件", score)
                else:
                    print(f"[监控] 文件安全: {file_path}")
            except Exception as e:
                print(f"[监控] 扫描文件失败 {file_path}: {e}")

    def _send_alert_notification(self, file_path, threat_type, score):
        filename = os.path.basename(file_path)
        msg = f"⚠ 监控发现{threat_type}: {filename} (评分:{score})"
        if ui_root and ui_content_frame:
            ui_root.after(0, lambda: _show_alert_banner(msg, "#d93025", score))


def start_monitor_mode(monitor_path, antivirus_instance):
    if not os.path.exists(monitor_path):
        print(f"[!] 监控路径不存在: {monitor_path}")
        return False
    print(f"[*] 启动文件监控模式")
    print(f"[*] 监控目录: {monitor_path}")
    print(f"[*] 当有新文件出现时会自动扫描")
    event_handler = AutoScanHandler(antivirus_instance)
    observer = Observer()
    observer.schedule(event_handler, monitor_path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[*] 停止文件监控...")
        observer.stop()
    observer.join()
    return True


class ProcessScanner:
    """进程扫描器 - 用于检测恶意进程"""

    def __init__(self):
        self.suspicious_process_names = [
            r'(?i)(svchost.*exe)', r'(?i)(lsass.*exe)', r'(?i)(csrss.*exe)',
            r'(?i)(smss.*exe)', r'(?i)(winlogon.*exe)', r'(?i)(services.*exe)',
            r'(?i)(explorer.*exe)', r'(?i)(rundll32.*exe)', r'(?i)(wscript.*exe)',
            r'(?i)(cscript.*exe)', r'(?i)(powershell.*exe)', r'(?i)(cmd.*exe)',
        ]
        self.suspicious_process_paths = [
            r'(?i)(temp\\|tmp\\)', r'(?i)(appdata\\local\\temp\\)',
            r'(?i)(windows\\temp\\)', r'(?i)(users\\.*\\appdata\\local\\temp\\)',
        ]
        self.system_process_whitelist = [
            'System', 'System Idle Process', 'Registry', 'smss.exe', 'csrss.exe',
            'wininit.exe', 'services.exe', 'lsass.exe', 'svchost.exe',
            'taskhost.exe', 'dwm.exe', 'explorer.exe', 'conhost.exe', 'spoolsv.exe',
        ]
        self.mining_process_patterns = [
            r'(?i)(xmrig|ccminer|ethminer|claymore|nicehash|miner)',
            r'(?i)(crypto.*miner|bitcoin.*miner)',
        ]
        self.suspicious_cmdline_patterns = [
            r'(?i)(-o\s+.*pool.*)', r'(?i)(--url\s+.*pool.*)',
            r'(?i)(-u\s+.*wallet.*)', r'(?i)(-p\s+.*x)',
            r'(?i)(--user\s+.*wallet.*)', r'(?i)(--pass\s+.*x)',
            r'(?i)(stratum\+tcp://)', r'(?i)(-k\s+--donate-level)',
        ]

    def scan_running_processes(self):
        suspicious_processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline', 'username', 'create_time']):
                try:
                    process_info = proc.info
                    pid = process_info['pid']
                    name = process_info['name'] or ''
                    exe_path = process_info['exe'] or ''
                    cmdline = process_info['cmdline'] or []
                    username = process_info['username'] or ''
                    is_suspicious, findings = self._analyze_process(pid, name, exe_path, cmdline, username)
                    if is_suspicious:
                        suspicious_processes.append({
                            'pid': pid, 'name': name, 'exe_path': exe_path,
                            'cmdline': cmdline, 'username': username, 'findings': findings
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"[!] 扫描进程时出错: {e}")
        return suspicious_processes

    def _analyze_process(self, pid, name, exe_path, cmdline, username):
        findings, score = [], 0
        ns, nf = self._check_process_name(name); score += ns; findings.extend(nf)
        ps, pf = self._check_process_path(exe_path); score += ps; findings.extend(pf)
        cs, cf = self._check_command_line(cmdline); score += cs; findings.extend(cf)
        bs, bf = self._check_process_behavior(pid); score += bs; findings.extend(bf)
        ms, mf = self._check_process_memory(pid); score += ms; findings.extend(mf)
        ns2, nf2 = self._check_network_connections(pid); score += ns2; findings.extend(nf2)
        return score > 30, findings

    def _check_process_name(self, process_name):
        score, findings = 0, []
        pnl = process_name.lower()
        if pnl in [p.lower() for p in self.system_process_whitelist]:
            return score, findings
        for pattern in self.suspicious_process_names:
            if re.search(pattern, process_name):
                score += 10; findings.append(f"可疑进程名: {process_name}"); break
        for pattern in self.mining_process_patterns:
            if re.search(pattern, process_name):
                score += 30; findings.append(f"可能为挖矿进程: {process_name}"); break
        return score, findings

    def _check_process_path(self, exe_path):
        score, findings = 0, []
        if not exe_path: return score, findings
        epl = exe_path.lower()
        for pattern in self.suspicious_process_paths:
            if re.search(pattern, epl):
                score += 20; findings.append(f"进程位于可疑路径: {exe_path}"); break
        temp_dirs = [os.environ.get('TEMP', '').lower(), os.environ.get('TMP', '').lower(),
                     'c:\\windows\\temp', 'c:\\users\\*\\appdata\\local\\temp']
        for td in temp_dirs:
            if td and td in epl:
                score += 15; findings.append(f"进程位于临时目录: {exe_path}"); break
        return score, findings

    def _check_command_line(self, cmdline):
        score, findings = 0, []
        if not cmdline: return score, findings
        cs = ' '.join(cmdline).lower()
        for pattern in self.suspicious_cmdline_patterns:
            if re.search(pattern, cs):
                score += 25; findings.append(f"可疑命令行参数匹配: {pattern}"); break
        suspicious_flags = ['--mining', '--pool', '--wallet', '--stratum',
                            '-o', '-u', '-p', '--url', '--user', '--pass', '--cuda', '--opencl']
        for flag in suspicious_flags:
            if flag in cs:
                score += 10; findings.append(f"可疑命令行标志: {flag}"); break
        return score, findings

    def _check_process_behavior(self, pid):
        score, findings = 0, []
        try:
            proc = psutil.Process(pid)
            cpu = proc.cpu_percent(interval=0.1)
            if cpu > 80: score += 15; findings.append(f"高CPU使用率: {cpu}%")
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            if mem_mb > 500: score += 10; findings.append(f"高内存使用: {mem_mb:.2f} MB")
            if proc.num_threads() > 100: score += 10; findings.append(f"线程数过多: {proc.num_threads()}")
            if proc.num_handles() > 1000: score += 10; findings.append(f"句柄数过多: {proc.num_handles()}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            pass
        return score, findings

    def _check_process_memory(self, pid):
        score, findings = 0, []
        try:
            if not self._is_admin(): return score, findings
            proc = psutil.Process(pid)
            exec_regions = sum(1 for mm in proc.memory_maps() if 'x' in mm.perms)
            if exec_regions > 5: score += 20; findings.append(f"发现 {exec_regions} 个可执行内存区域")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            pass
        return score, findings

    def _check_network_connections(self, pid):
        score, findings = 0, []
        try:
            proc = psutil.Process(pid)
            suspicious_ports = [3333, 4444, 5555, 6666, 7777, 8888, 9999, 8333, 9333]
            mining_pools = ['stratum', 'pool', 'mining', 'xmrpool', 'nanopool']
            for conn in proc.connections():
                if hasattr(conn, 'raddr') and conn.raddr:
                    ip, port = conn.raddr
                    if port in suspicious_ports: score += 20; findings.append(f"连接到可疑端口: {port}")
                    try:
                        import socket
                        hostname = socket.gethostbyaddr(ip)[0] if ip else ''
                        for pool in mining_pools:
                            if pool in hostname.lower():
                                score += 30; findings.append(f"连接到挖矿池: {hostname}"); break
                    except:
                        pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception:
            pass
        return score, findings

    def _is_admin(self):
        try: return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except: return False

    def kill_malicious_process(self, pid):
        # 优先走内核驱动（能杀顽固进程），驱动没加载/失败再退回用户态
        try:
            from AtivirusKernelIO import IO
            with IO() as kio:
                kio.kill_process(pid)
            return True, f"进程 {pid} 已由内核驱动结束"
        except Exception:
            pass
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            try:
                proc.wait(timeout=5); return True, f"进程 {pid} 已结束"
            except psutil.TimeoutExpired:
                proc.kill(); return True, f"进程 {pid} 已被强制结束"
        except psutil.NoSuchProcess: return True, f"进程 {pid} 不存在"
        except psutil.AccessDenied: return False, f"无权限结束进程 {pid}，请以管理员身份运行"
        except Exception as e: return False, f"结束进程 {pid} 失败: {str(e)}"


class HeuristicScanner:
    """启发式扫描器 - 深度检测恶意代码"""

    def __init__(self):
        self.malicious_patterns = {
            'suspicious_strings': [
                r'(?i)(malware|trojan|virus|worm|ransomware|spyware|adware|rootkit|backdoor|botnet)',
                r'(?i)(keylogger|rat|remote.*access|exploit|payload|shellcode)',
                r'(?i)(format.*c:|del.*/.*/.*/.*|rm.*-rf|shutdown.*/s|taskkill.*/f)',
                r'(?i)(reg.*add.*HKLM|reg.*add.*HKCU|reg.*add.*run)',
                r'(?i)(powershell.*-e|powershell.*-enc|certutil.*-decode|Invoke-Expression|IEX\()',
                r'http[s]?://(?!.*(microsoft|windowsupdate|adobe|apple|mozilla))[^\s]+',
                r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b:\d{1,5}',
                r'(?i)(\bmining\b|\bcryptominer\b|\bcrypto.*miner\b|\bxmrig\b)',
                # === 新增：勒索软件特征 ===
                r'(?i)(encrypt.*file|decrypt.*file|ransom|bitcoin|monero|wallet\.dat)',
                r'(?i)(\.encrypted|\.locky|\.wncry|\.crypt|\.crab|\.cerber|\.zepto)',
                # === 新增：反虚拟机/反调试 ===
                r'(?i)(vbox|vmware|qemu|virtualbox|sandboxie|sandbox)',
                r'(?i)(IsDebuggerPresent|CheckRemoteDebuggerPresent|NtQueryInformationProcess)',
                r'(?i)(OutputDebugString|NtSetInformationThread|HideThreadFromDebugger)',
                # === 新增：持久化机制 ===
                r'(?i)(schtasks.*\/create|sc\s+create|CreateService|StartService)',
                r'(?i)(HKEY_LOCAL_MACHINE\\\\(SOFTWARE|SYSTEM).*Run)',
                r'(?i)(Startup|Start Menu\\\\Programs\\\\Startup)',
            ],
            'suspicious_functions': [
                'CreateRemoteThread', 'WriteProcessMemory', 'VirtualAllocEx',
                'SetWindowsHookEx', 'keybd_event', 'mouse_event',
                'URLDownloadToFile', 'ShellExecute', 'WinExec',
                'RegSetValueEx', 'RegCreateKey', 'CreateService',
                'OpenProcessToken', 'AdjustTokenPrivileges',
                # === 新增：高危API ===
                'NtCreateThreadEx', 'RtlCreateUserThread', 'QueueUserAPC',
                'SetThreadContext', 'NtUnmapViewOfSection', 'ZwUnmapViewOfSection',
                'CryptAcquireContext', 'CryptEncrypt', 'CryptDecrypt',
                'OpenProcess', 'ReadProcessMemory', 'NtReadVirtualMemory',
                'SetFileAttributesW', 'MoveFileEx', 'DeleteFileW',
                'InternetOpenUrl', 'InternetReadFile', 'URLDownloadToFileW',
            ],
            'suspicious_extensions': ['.bat', '.cmd', '.ps1', '.vbs', '.js', '.jar'],
            'sensitive_directories': [
                'Windows\\System32', 'Windows\\SysWOW64',
                'AppData', 'Temp', 'Temporary',
                'Start Menu\\Programs\\Startup',
                'Microsoft\\Windows\\Start Menu\\Programs\\Startup'
            ],
            # === 新增：高危导入DLL组合（进程注入特征）===
            'injection_combo_dlls': [
                ('kernel32.dll', 'VirtualAllocEx', 'WriteProcessMemory', 'CreateRemoteThread'),
                ('ntdll.dll', 'NtCreateThreadEx', 'NtWriteVirtualMemory'),
                ('kernel32.dll', 'OpenProcess', 'VirtualAllocEx', 'CreateRemoteThread'),
            ],
            # === 新增：已知恶意壳特征 ===
            'packer_signatures': {
                '.vmp': 'VMProtect 加壳',
                '.vmp0': 'VMProtect 加壳',
                '.vmp1': 'VMProtect 加壳',
                '.themida': 'Themida 加壳',
                '.aspack': 'ASPack 加壳',
                '.upx0': 'UPX 加壳',
                '.upx1': 'UPX 加壳',
                '.enigma': 'Enigma Protector',
                '.mackt': 'MACKT 加壳',
                '.obsidium': 'Obsidium 加壳',
                '.petite': 'Petite 加壳',
                '.winlice': 'WinLicense 加壳',
                '.sforce': 'StarForce 加壳',
            },
            # === 新增：可疑节权限 ===
            'suspicious_section_names': [
                '.textbss', '.crt', '.win32', '.new', '.unknown',
                '.dcrpt', '.enc', '.patch', '.xyz', 'UPX!', 'MPRESS',
            ],
        }

        # YARA 规则：数据驱动，从 yara_rules.json 加载（文件缺失则空规则，扫描不受影响）
        self.yara_rules = []
        try:
            rules_path = resource_path("yara_rules.json")
            if os.path.exists(rules_path):
                with open(rules_path, "r", encoding="utf-8") as f:
                    self.yara_rules = json.load(f)
        except Exception as e:
            print(f"[!] YARA规则加载失败: {e}")

        # === 新增：已知病毒哈希快速匹配 ===
        self.known_bad_hashes = {
            # 常见勒索软件/木马的片段特征
            'ransom_note_patterns': [
                b'YOUR FILES ARE ENCRYPTED',
                b'All your files have been encrypted',
                b'How to decrypt',
                b'buy bitcoin',
                b'payment must be made',
                b'DECRYPT_INSTRUCTIONS',
                b'YOUR COMPUTER HAS BEEN LOCKED',
            ],
            'miner_pool_domains': [
                'pool.minexmr.com', 'xmrpool.eu', 'nanopool.org',
                'minexmr.com', 'supportxmr.com', 'c3pool.com',
                'pool.hashvault.pro', 'moneroocean.stream',
            ],
        }

        self.file_signatures = {
            b'MZ': ('PE executable', '.exe'), b'\x7fELF': ('ELF executable', ''),
            b'#!': ('Script', ''), b'%PDF': ('PDF', '.pdf'),
            b'\x89PNG\r\n\x1a\n': ('PNG image', '.png'), b'\xff\xd8\xff': ('JPEG image', '.jpg'),
            b'GIF87a': ('GIF image', '.gif'), b'GIF89a': ('GIF image', '.gif'),
            b'BM': ('BMP image', '.bmp'), b'PK\x03\x04': ('ZIP archive', '.zip'),
            b'PK\x05\x06': ('ZIP archive', '.zip'), b'PK\x07\x08': ('ZIP archive', '.zip'),
            b'Rar!\x1a\x07\x00': ('RAR archive', '.rar'), b'\x1f\x8b\x08': ('GZIP archive', '.gz'),
            b'BZh': ('BZIP2 archive', '.bz2'), b'\xfd7zXZ\x00': ('XZ archive', '.xz'),
            b'<?xml': ('XML document', '.xml'), b'<html': ('HTML document', '.html'),
        }
        self.image_signatures = {
            b'\xff\xd8\xff': 'jpg', b'\x89PNG\r\n\x1a\n': 'png',
            b'GIF87a': 'gif', b'GIF89a': 'gif', b'BM': 'bmp',
        }

    # ========== 新增：数字签名验证 ==========
    def _check_digital_signature(self, filepath):
        """检查PE文件是否有有效数字签名（Microsoft签名=安全，无签名=可疑）"""
        score, findings = 0, []
        try:
            import win32security
            import win32api
            # 尝试获取文件签名
            filepath_wide = filepath
            try:
                cert = win32security.WinVerifyTrust(None, filepath_wide)
                # 有签名 → 不扣分
                return 0, []
            except:
                # 无签名或验证失败
                fn = os.path.basename(filepath).lower()
                ext = os.path.splitext(filepath)[1].lower()
                if ext in ['.exe', '.dll', '.sys']:
                    fpl = filepath.lower()
                    # System32 里无签名的 PE 文件 → 高度可疑
                    if 'system32' in fpl or 'syswow64' in fpl:
                        score += 30
                        findings.append("System32中的PE文件无数字签名（正常系统文件应有Microsoft签名）")
                    elif 'windows' in fpl:
                        score += 15
                        findings.append("Windows目录中的PE文件无数字签名")
        except ImportError:
            pass  # pywin32 不可用时跳过
        except Exception:
            pass
        return score, findings

    # ========== 新增：PE深度分析 ==========
    def _analyze_pe_deep(self, content, filepath):
        """深度PE分析：时间戳异常、导入表组合、资源异常"""
        score, findings = 0, []
        try:
            pe = pefile.PE(data=content)
            # --- 时间戳检测 ---
            if hasattr(pe, 'FILE_HEADER'):
                ts = pe.FILE_HEADER.TimeDateStamp
                import datetime
                try:
                    ft = datetime.datetime.fromtimestamp(ts)
                    now = datetime.datetime.now()
                    # 未来时间戳（可能是恶意伪造）
                    if ft > now:
                        score += 25
                        findings.append(f"PE时间戳异常(未来时间): {ft}")
                    # 过于古老但不在Windows目录 → 可疑
                    if ft.year < 2010 and 'windows' not in filepath.lower():
                        score += 5
                        findings.append(f"PE时间戳过旧({ft.year}年)")
                except:
                    pass

            # --- 高危导入表组合检测 ---
            if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
                imported_funcs = set()
                for entry in pe.DIRECTORY_ENTRY_IMPORT:
                    dll_name = entry.dll.decode('utf-8', errors='ignore').lower()
                    for imp in entry.imports:
                        if imp.name:
                            imported_funcs.add(imp.name.decode('utf-8', errors='ignore'))

                # 进程注入三件套
                if {'VirtualAllocEx', 'WriteProcessMemory', 'CreateRemoteThread'} & imported_funcs:
                    if 'VirtualAllocEx' in imported_funcs and 'CreateRemoteThread' in imported_funcs:
                        score += 40
                        findings.append("检测到进程注入API组合(VirtualAllocEx+CreateRemoteThread)")
                    elif len({'VirtualAllocEx', 'WriteProcessMemory', 'CreateRemoteThread'} & imported_funcs) >= 2:
                        score += 25
                        findings.append("检测到可疑内存操作API组合")

                # 键盘记录
                if 'SetWindowsHookEx' in imported_funcs and 'GetMessage' in imported_funcs:
                    score += 20
                    findings.append("检测到可能的键盘记录(SetWindowsHookEx+GetMessage)")

                # 下载执行
                if 'URLDownloadToFile' in imported_funcs and ('ShellExecute' in imported_funcs or 'WinExec' in imported_funcs):
                    score += 35
                    findings.append("检测到下载执行组合(URLDownloadToFile+执行API)")

            # --- 节名称检测 ---
            if hasattr(pe, 'sections'):
                for sec in pe.sections:
                    sn = sec.Name.decode('utf-8', errors='ignore').strip('\x00').lower()
                    # 已知壳
                    for pack_name, pack_desc in self.malicious_patterns['packer_signatures'].items():
                        if pack_name in sn:
                            score += 40
                            findings.append(f"发现{pack_desc}节: {sn}")
                            break
                    # 可写可执行节
                    if sec.Characteristics & 0xE0000020:
                        score += 30
                        findings.append(f"危险节权限(可写可执行): {sn}")
                    # 可疑节名
                    for bad_name in self.malicious_patterns['suspicious_section_names']:
                        if bad_name.lower() in sn:
                            score += 15
                            findings.append(f"可疑节名: {sn}")
                            break

            # --- 入口点异常 ---
            if hasattr(pe, 'OPTIONAL_HEADER'):
                ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
                if ep == 0:
                    score += 35
                    findings.append("入口点为0(可能为恶意壳/加载器)")
                # 入口点不在代码节中
                if hasattr(pe, 'sections'):
                    ep_in_section = False
                    for sec in pe.sections:
                        va = sec.VirtualAddress
                        vs = sec.Misc_VirtualSize
                        if va <= ep < va + vs and b'.text' in sec.Name:
                            ep_in_section = True
                            break
                    if not ep_in_section:
                        score += 20
                        findings.append("入口点不在.text代码节(可能被篡改)")

            # --- ImageBase异常（某些恶意软件使用非标准基址）---
            if hasattr(pe, 'OPTIONAL_HEADER'):
                ib = pe.OPTIONAL_HEADER.ImageBase
                # 正常的EXE基址是0x400000，DLL是0x10000000
                ext = os.path.splitext(filepath)[1].lower()
                if ext == '.exe' and ib != 0x400000 and ib != 0x140000000:
                    score += 10
                    findings.append(f"非标准ImageBase: 0x{ib:X}")

            # --- TLS回调（恶意软件常用作反调试）---
            if hasattr(pe, 'DIRECTORY_ENTRY_TLS'):
                try:
                    tls = pe.DIRECTORY_ENTRY_TLS.struct
                    if tls.AddressOfCallBacks and tls.AddressOfCallBacks != 0:
                        score += 25
                        findings.append("存在TLS回调(常用于反调试/反虚拟机)")
                except:
                    pass

            pe.close()
        except Exception as e:
            pass  # 非PE文件会失败，正常
        return score, findings

    # ========== 新增：反虚拟机检测 ==========
    def _check_anti_vm(self, content, filepath):
        """检测反虚拟机/反沙箱特征"""
        score, findings = 0, []
        try:
            # 以文本方式搜索反VM字符串
            text = content.decode('latin-1', errors='ignore')
            vm_strings = [
                'VBoxService.exe', 'vboxmouse.sys', 'vboxguest.sys', 'vboxsf.sys',
                'vmware.exe', 'vmwareservice.exe', 'vmmouse.sys', 'vmci.sys',
                'qemu-ga.exe', 'qemuwmi.dll',
                'sandboxiedcomlaunch.exe', 'sbiedll.dll',
                'procmon.exe', 'wireshark.exe', 'fiddler.exe',
                'x64dbg.exe', 'x32dbg.exe', 'ollydbg.exe', 'ida.exe', 'ida64.exe',
                'dbghelp.dll is loaded',
                r'\\\\.\\VBoxGuest', r'\\\\.\\VBoxMiniRdr',
                r'\\\\.\\vmci', 'VMware Virtual',
            ]
            for s in vm_strings:
                if s.lower() in text.lower():
                    score += 15
                    findings.append(f"检测到反虚拟机/反调试字符串: {s}")
                    break
        except:
            pass
        return score, findings

    # ========== 新增：勒索软件特征 ==========
    def _check_ransomware(self, content, filepath):
        """检测勒索软件特征"""
        score, findings = 0, []
        try:
            text = content.decode('latin-1', errors='ignore')
            # 勒索信模式
            for pattern in self.known_bad_hashes['ransom_note_patterns']:
                try:
                    if pattern in content:
                        score += 50
                        findings.append(f"发现勒索软件通知文本: {pattern.decode('ascii','ignore')[:40]}")
                        break
                except:
                    if pattern.lower() in content.lower():
                        score += 50
                        findings.append("发现疑似勒索软件通知文本")
                        break

            # 加密文件扩展名列表（勒索软件常用）
            crypto_exts = ['.aes', '.locked', '.encrypted', '.cry', '.crypt', '.crab',
                          '.cerber', '.zepto', '.locky', '.wncry', '.wcry', '.wncrypt',
                          '.odcodc', '.shadow', '.enc', '.cryptolocker', '.thor']
            ext_score = 0
            for ext in crypto_exts:
                if ext.encode() in content.lower():
                    ext_score += 5
            if ext_score > 20:
                score += 30
                findings.append(f"发现大量加密文件扩展名引用(勒索软件特征)")

            # vssadmin删除卷影副本
            if 'vssadmin' in text.lower() and ('delete' in text.lower() and 'shadow' in text.lower()):
                score += 35
                findings.append("检测到卷影副本删除命令(勒索软件行为)")

            # 比特币地址
            if re.search(r'[13][a-km-zA-HJ-NP-Z1-9]{25,34}', text):
                score += 10
                findings.append("发现比特币地址")

        except:
            pass
        return score, findings

    def analyze_file_content(self, filepath, max_size=10*1024*1024):
        score, findings = 0, []
        try:
            file_size = os.path.getsize(filepath)
            if file_size > max_size: return 0, ["文件过大，跳过内容分析"], 0
            with open(filepath, 'rb') as f: content = f.read()

            # Temp 目录的文件跳过重型分析（多半是安装包/编译产物）
            is_temp = 'temp' in filepath.lower() or 'tmp' in filepath.lower()

            is_bin = self._is_binary(content)
            if is_bin:
                bs, bf = self._analyze_binary(content, filepath); score += bs; findings.extend(bf)
                if self._is_pe_file(content):
                    ds, df = self._analyze_pe_deep(content, filepath); score += ds; findings.extend(df)
            else:
                try:
                    tc = content.decode('utf-8', errors='ignore')
                    ts, tf = self._analyze_text(tc, filepath); score += ts; findings.extend(tf)
                except: pass

            vs, vf = self._check_anti_vm(content, filepath); score += vs; findings.extend(vf)
            rs, rf = self._check_ransomware(content, filepath); score += rs; findings.extend(rf)
            ys, yf = self._match_yara_rules(content, filepath); score += ys; findings.extend(yf)
            if is_bin:
                ps, pf = self._check_pe_anomalies(content, filepath); score += ps; findings.extend(pf)
            entropy = self._calculate_entropy(content)
            if entropy > 7.5: score += 20; findings.append(f"文件熵值过高 ({entropy:.2f})，可能被加密或混淆")
            findings.extend(self._check_file_type(content, filepath))
        except Exception as e:
            findings.append(f"分析文件时出错: {str(e)}")
        return score, findings, len(findings)

    def _is_binary(self, data):
        text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20,0x100)) - {0x7f})
        if not data: return False
        return sum(1 for b in data[:1024] if b not in text_chars) / min(len(data), 1024) > 0.3

    def _analyze_binary(self, content, filepath):
        score, findings = 0, []
        try:
            if self._is_pe_file(content):
                ps, pf = self._analyze_pe_file(content, filepath); score += ps; findings.extend(pf)
            ms, mf = self._check_malicious_patterns(content); score += ms; findings.extend(mf)
            ss, sf = self._extract_strings(content); score += ss; findings.extend(sf)
        except Exception as e: findings.append(f"二进制分析出错: {str(e)}")
        return score, findings

    def _analyze_text(self, text_content, filepath):
        score, findings = 0, []
        for pattern in self.malicious_patterns['suspicious_strings']:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            if matches:
                score += 10 * len(matches)
                for m in matches[:3]: findings.append(f"发现可疑字符串: {m}")
        for func in self.malicious_patterns['suspicious_functions']:
            if func in text_content: score += 15; findings.append(f"发现可疑函数调用: {func}")
        b64 = re.findall(r'[A-Za-z0-9+/]{20,}={0,2}', text_content)
        if b64 and len(b64) > 5: score += 20; findings.append(f"发现大量Base64编码 ({len(b64)}处)")
        hex_m = re.findall(r'[0-9A-Fa-f]{20,}', text_content)
        if hex_m and len(hex_m) > 3: score += 15; findings.append(f"发现长十六进制字符串 ({len(hex_m)}处)")
        return score, findings

    def _is_pe_file(self, content): return len(content)>2 and content[:2]==b'MZ'

    def _analyze_pe_file(self, content, filepath):
        score, findings = 0, []
        try:
            pe = pefile.PE(data=content, fast_load=True)
            if hasattr(pe, 'OPTIONAL_HEADER') and pe.OPTIONAL_HEADER.AddressOfEntryPoint==0:
                score+=30; findings.append("入口点为0，可能为壳或混淆")
            if hasattr(pe, 'sections'):
                for sec in pe.sections:
                    sn = sec.Name.decode('utf-8',errors='ignore').strip('\x00')
                    if sn in ['.vmp','.themida','.aspack','.upx']: score+=40; findings.append(f"发现加壳节: {sn}")
                    if sec.Characteristics & 0xE0000020: score+=25; findings.append(f"节可写可执行: {sn}")
            if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
                for entry in pe.DIRECTORY_ENTRY_IMPORT:
                    dn = entry.dll.decode('utf-8',errors='ignore').lower()
                    if dn in ['kernel32.dll','user32.dll','advapi32.dll','ws2_32.dll','wininet.dll','urlmon.dll']:
                        score+=5; findings.append(f"导入可疑DLL: {dn}")
            pe.close()
        except Exception as e: findings.append(f"PE文件分析出错: {str(e)}")
        return score, findings

    def _check_malicious_patterns(self, content):
        score, findings = 0, []
        hc = content.hex()
        for p in ['31c0','31db','31c9','31d2','cd80','b8']:
            if p in hc: score+=20; findings.append(f"发现可能的shellcode模式: {p}"); break
        return score, findings

    def _extract_strings(self, content, min_len=4):
        score, findings = 0, []
        try:
            strings, cur = [], []
            for b in content:
                if 32<=b<=126: cur.append(chr(b))
                else:
                    if len(cur)>=min_len: strings.append(''.join(cur))
                    cur=[]
            if len(cur)>=min_len: strings.append(''.join(cur))
            for s in strings[:50]:
                sl = s.lower()
                if ('http://' in sl or 'https://' in sl) and not any(d in sl for d in ['microsoft','windowsupdate','adobe']):
                    score+=15; findings.append(f"发现可疑URL: {s[:100]}")
                for cmd in ['format','del ','rm ','shutdown','taskkill','reg add']:
                    if cmd in sl: score+=10; findings.append(f"发现可疑命令: {s[:100]}"); break
                if 'system32' in sl or 'temp\\' in sl or 'startup' in sl:
                    score+=5; findings.append(f"发现可疑路径: {s[:100]}")
        except Exception as e: findings.append(f"字符串提取出错: {str(e)}")
        return score, findings

    def _calculate_entropy(self, data):
        if not data: return 0
        counter = Counter(data)
        return -sum((c/len(data))*math.log2(c/len(data)) for c in counter.values())

    def _check_file_type(self, content, filepath):
        findings = []
        try:
            dt = self._detect_file_signature(content)
            ext = os.path.splitext(filepath)[1].lower()
            if dt:
                ft, ee = dt
                if ext and ee and ext!=ee: findings.append(f"文件扩展名({ext})与实际类型({ft})不匹配")
                if ft=='PE executable' and ext not in ['.exe','.dll','.sys','.scr']:
                    findings.append(f"可执行文件使用了非标准扩展名: {ext}")
            elif ext in ['.exe','.dll','.sys'] and not self._is_pe_file(content):
                findings.append(f"文件扩展名({ext})但实际不是可执行文件")
            if ext in ['.jpg','.jpeg','.png','.gif','.bmp','.tiff','.tif','.ico']:
                img_type = self._detect_image_type(content[:32])
                if img_type:
                    ewod = ext.lstrip('.')
                    if ewod not in img_type and img_type not in ewod:
                        findings.append(f"图片文件可能被伪装: 扩展名{ext}, 检测类型{img_type}")
                else:
                    findings.append(f"文件有图片扩展名{ext}但实际不是图片")
        except Exception as e: findings.append(f"文件类型检测出错: {str(e)}")
        return findings

    def _detect_file_signature(self, data):
        if len(data)<4: return None
        for sig,(ft,ee) in self.file_signatures.items():
            if data[:len(sig)]==sig: return (ft,ee)
        return None

    def _detect_image_type(self, data):
        for sig,it in self.image_signatures.items():
            if data.startswith(sig): return it
        return None

    # ========== 新增：YARA式规则引擎 ==========
    def _match_yara_rules(self, content, filepath):
        """YARA风格的规则匹配引擎——已知恶意软件家族特征"""
        score, findings = 0, []
        rules = self.yara_rules  # 数据驱动：规则从 resources/yara_rules.json 加载

        try:
            text = content.decode('latin-1', errors='ignore')
            for rule in rules:
                matches = 0
                matched_strs = []
                for s in rule['strings']:
                    if isinstance(s, str):
                        s = s.encode('utf-8')  # JSON 里是 str，转成 bytes 再匹配
                    if s in content:
                        matches += 1
                        matched_strs.append(s.decode('ascii', errors='ignore')[:30])

                cond = rule['condition']
                if cond == 'any1' and matches >= 1:
                    score += rule['score']
                    findings.append(f"YARA规则命中: {rule['name']} → {matched_strs[0]}")
                elif cond == 'any2' and matches >= 2:
                    score += rule['score']
                    findings.append(f"YARA规则命中: {rule['name']} (匹配{matches}个特征)")
                elif cond == 'any3' and matches >= 3:
                    score += rule['score']
                    findings.append(f"YARA规则命中: {rule['name']} (匹配{matches}个特征)")
                elif isinstance(cond, int) and matches >= cond:
                    score += rule['score']
                    findings.append(f"YARA规则命中: {rule['name']} (匹配{matches}/{cond}个特征)")
        except:
            pass
        return score, findings

    # ========== 新增：ClamAV风格PE结构异常检测 ==========
    def _check_pe_anomalies(self, content, filepath):
        """PE结构异常检测——参考ClamAV的检查逻辑"""
        score, findings = 0, []
        try:
            if not self._is_pe_file(content):
                return score, findings

            pe = pefile.PE(data=content)

            # 1. 节数量异常（正常PE很少超过15个节）
            if hasattr(pe, 'FILE_HEADER'):
                ns = pe.FILE_HEADER.NumberOfSections
                if ns == 0:
                    score += 35; findings.append(f"PE节数量为0(损坏的PE文件)")
                elif ns > 20:
                    score += 20; findings.append(f"PE节数量异常({ns}个节)")
                elif ns > 12:
                    score += 5; findings.append(f"PE节数量偏多({ns}个节)")

            # 2. SizeOfOptionalHeader 异常
            if hasattr(pe, 'FILE_HEADER'):
                soh = pe.FILE_HEADER.SizeOfOptionalHeader
                if soh < 0xE0:  # PE32最小可选头
                    score += 25; findings.append(f"PE可选头过小(0x{soh:X})")

            # 3. 入口点RVA异常
            if hasattr(pe, 'OPTIONAL_HEADER'):
                ep = pe.OPTIONAL_HEADER.AddressOfEntryPoint
                # 入口点不在任何节内
                ep_found = False
                for sec in pe.sections:
                    va = sec.VirtualAddress
                    vs = sec.Misc_VirtualSize
                    if va <= ep < va + vs:
                        ep_found = True
                        break
                if not ep_found and ep != 0:
                    score += 30; findings.append("入口点不在任何节内")

            # 4. 节的文件偏移/RVA不匹配
            for sec in pe.sections:
                # 节的RawSize > VirtualSize 是加壳指标
                if sec.SizeOfRawData > sec.Misc_VirtualSize * 2 and sec.SizeOfRawData > 0x1000:
                    score += 15; findings.append(f"节{sec.Name.decode('ascii','ignore').strip(chr(0))}的原始大小异常(可能是overlay)")

            # 5. 资源节过大（捆绑文件）
            for sec in pe.sections:
                sn = sec.Name.decode('utf-8', errors='ignore').strip('\x00').lower()
                if '.rsrc' in sn and sec.SizeOfRawData > 5 * 1024 * 1024:
                    score += 20; findings.append("资源节过大(>5MB，可能捆绑文件)")

            pe.close()
        except:
            pass
        return score, findings

    def check_file_behavior(self, filepath):
        score, findings = 0, []
        try:
            fn = os.path.basename(filepath).lower()
            for name in ['svchost','lsass','csrss','smss','winlogon','update','installer','setup','patch','crack','keygen','loader','injector','hook','bypass']:
                if name in fn: score+=10; findings.append(f"可疑文件名包含: {name}"); break
            fpl = filepath.lower()
            for sd in self.malicious_patterns['sensitive_directories']:
                if sd.lower() in fpl:
                    # System32/Temp 加5分（正常文件多），其他加15分
                    if 'system32' in sd.lower() or 'syswow64' in sd.lower() or 'temp' in sd.lower():
                        score += 5
                    else:
                        score += 15
                    findings.append(f"文件位于敏感目录: {sd}"); break
            ext = os.path.splitext(filepath)[1].lower()
            if ext in self.malicious_patterns['suspicious_extensions']: score+=5; findings.append(f"可疑文件扩展名: {ext}")
            if os.name=='nt':
                FA_HIDDEN, FA_SYSTEM = 0x2, 0x4
                attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                if attrs!=-1 and (attrs & (FA_HIDDEN|FA_SYSTEM)): score+=20; findings.append("文件具有隐藏或系统属性")
            # === 新增：数字签名验证 ===
            ds, df = self._check_digital_signature(filepath); score += ds; findings.extend(df)
            fs = os.path.getsize(filepath)
            if ext in ['.exe','.dll']:
                if fs<1024: score+=30; findings.append("可执行文件过小，可能为下载器")
                elif fs>50*1024*1024: score+=20; findings.append("可执行文件过大，可能捆绑其他文件")
        except Exception as e: findings.append(f"行为分析出错: {str(e)}")
        return score, findings


# ==================== 自保护模块 ====================
def verify_integrity():
    """启动时校验：关键文件是否被篡改（读取构建时生成的签名）"""
    tampered = []
    try:
        manifest_path = resource_path("integrity.json")
        if os.path.exists(manifest_path):
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            for fname, expected_hash in manifest.items():
                if fname == "PYAntivirus.exe":
                    actual_path = sys.executable if hasattr(sys, '_MEIPASS') else None
                else:
                    actual_path = resource_path(fname)
                if actual_path and os.path.exists(actual_path):
                    with open(actual_path, 'rb') as f:
                        actual_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                    if actual_hash != expected_hash:
                        tampered.append((fname, expected_hash[:8], actual_hash[:8]))
    except Exception:
        pass
    return tampered


# 只有这些扩展名才跑启发式+ML，其他文件只做哈希匹配（速度提升5-10倍）
HEURISTIC_EXTS = {'.exe', '.dll', '.scr', '.sys', '.bat', '.cmd', '.vbs', '.vbe',
                  '.js', '.jse', '.ps1', '.hta', '.com', '.msi', '.ocx', '.jar',
                  '.docm', '.xlsm', '.pif', '.lnk'}


class AVEngine:
    def __init__(self, enable_heuristic=True):
        self.virus_db = set()  # 哈希集合，O(1)极速查找
        self.heuristic_scanner = HeuristicScanner() if enable_heuristic else None
        self.ml_scanner = MLScanner(ml_model_path()) if enable_heuristic else None
        self.process_scanner = ProcessScanner()
        self.stats = {"scanned": 0, "infected": 0, "suspicious": 0, "suspicious_processes": 0}
        self.infected_files = []
        self.suspicious_files = []
        self.suspicious_processes = []
        self.is_ui_mode = False
        self.scan_running = False
        self.scan_canceled = False
        self.heuristic_threshold = 50
        self.settings = {
            "virus_db_path": resource_path("virus_hash_lib.json"),
            "default_scan_path": "C:\\",
            "auto_delete": False,
            "auto_quarantine": False,
            "heuristic_enabled": True
        }

    def load_settings(self, settings_file="antivirus_settings.json"):
        if os.path.exists(settings_file):
            try:
                with open(settings_file,"r",encoding="utf-8") as f: saved=json.load(f)
                self.settings.update(saved); return True, "设置加载成功"
            except Exception as e: return False, f"加载设置失败: {e}"
        return False, "设置文件不存在"

    def save_settings(self, settings_file="antivirus_settings.json"):
        try:
            with open(settings_file,"w",encoding="utf-8") as f: json.dump(self.settings,f,indent=2,ensure_ascii=False)
            return True, "设置保存成功"
        except Exception as e: return False, f"保存设置失败: {e}"

    def load_virus_db(self, db_file=None):
        if db_file is None:
            db_file = self.settings.get("virus_db_path", resource_path("virus_hash_lib.json"))

        # 优先用极速文本格式（.txt）
        txt_file = db_file.replace('.json', '.txt')
        if os.path.exists(txt_file):
            self.virus_db = set()
            raw_count = 0
            with open(txt_file, 'r') as f:
                for line in f:
                    raw_count += 1
                    h = line.strip().lower()
                    if len(h) == 32:
                        self.virus_db.add(h)
            # 兜底：txt 疑似损坏（海量行但有效哈希极少）→ 回退 JSON
            if len(self.virus_db) >= 1000 or raw_count <= 10000:
                return True, f"成功加载 {len(self.virus_db)} 个MD5哈希特征(极速模式)"
            print(f"[!] 病毒库txt疑似损坏({raw_count}行仅{len(self.virus_db)}个有效哈希)，回退JSON")
            self.virus_db = set()

        # 回退到JSON格式
        if os.path.exists(db_file):
            with open(db_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.virus_db = set()
            for fp, hi in data.items():
                if isinstance(hi, dict) and 'hash' in hi:
                    hv = hi['hash'].lower()
                    if hi.get('algorithm', 'md5').lower() == 'md5':
                        self.virus_db.add(hv)
            return True, f"成功加载 {len(self.virus_db)} 个MD5哈希特征"
        return False, f"哈希库未找到: {db_file}"

    def calculate_hash(self, filepath, algorithm="md5"):
        hasher = {'md5': hashlib.md5(), 'sha1': hashlib.sha1(), 'sha256': hashlib.sha256()}.get(algorithm, hashlib.md5())
        try:
            with open(filepath,"rb") as f:
                while chunk:=f.read(8192): hasher.update(chunk)
            return hasher.hexdigest().lower()
        except: return None

    def scan_file(self, filepath, algorithm="md5"):
        fh = self.calculate_hash(filepath, algorithm)
        if fh and fh in self.virus_db: return "hash", fh, 100, ["已知病毒哈希匹配"], None
        if self.heuristic_scanner and os.path.splitext(filepath)[1].lower() in HEURISTIC_EXTS:
            bs,bf = self.heuristic_scanner.check_file_behavior(filepath)
            cs,cf,fc = self.heuristic_scanner.analyze_file_content(filepath)
            # ML 辅助评分
            ml_score = 0
            if self.ml_scanner:
                ml_score, ml_features = self.ml_scanner.predict(filepath)
                if ml_score > 30:
                    cf.append(f"ML模型评分: {ml_score}%")
            ts = bs + cs + int(ml_score * 2); af = bf + cf
            if ts >= self.heuristic_threshold: return "heuristic", None, ts, af, fh
        return None, None, 0, [], fh

    def scan_directory(self, path, progress_callback=None):
        infected_files, suspicious_files = [], []
        start_time = time.time()
        file_count, total_files = 0, 0
        for root, dirs, files in os.walk(path): total_files+=len(files)
        for root, dirs, files in os.walk(path):
            for file in files:
                if self.scan_canceled: break
                full_path=os.path.join(root,file); file_count+=1; self.stats["scanned"]=file_count
                if progress_callback and file_count%10==0:
                    progress_callback((file_count/total_files)*100, file_count, total_files)
                try:
                    st,vh,sc,fn2,fh2=self.scan_file(full_path,"md5")
                    if st=="hash":
                        self.stats["infected"]+=1
                        infected_files.append({"path":full_path,"type":"已知病毒","hash":vh,"score":sc,"findings":fn2})
                    elif st=="heuristic":
                        self.stats["suspicious"]+=1
                        suspicious_files.append({"path":full_path,"type":"可疑文件","hash":fh2,"score":sc,"findings":fn2})
                except Exception as e:
                    if self.is_ui_mode: print(f"[!] 扫描文件失败 {full_path}: {e}")
        self.infected_files=infected_files; self.suspicious_files=suspicious_files
        return infected_files+suspicious_files

    def generate_report(self, scan_results, output_file):
        report={"scan_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "scanned_files":self.stats["scanned"],"infected_files":self.stats["infected"],
                "suspicious_files":self.stats["suspicious"],
                "results":{"infected":self.infected_files,"suspicious":self.suspicious_files}}
        with open(output_file,"w",encoding="utf-8") as f: json.dump(report,f,indent=2,ensure_ascii=False)
        return output_file

    def on_notification_clicked(self, toast):
        if self.is_ui_mode:
            self._show_threat_action_ui()

    def _show_threat_action_ui(self):
        """在现代UI中显示威胁处理界面"""
        total = len(self.infected_files)+len(self.suspicious_files)
        if total == 0:
            msg_info("提示", "没有发现威胁文件")
            return
        choice = msg_ask("威胁处理", f"发现 {len(self.infected_files)} 个病毒文件\n发现 {len(self.suspicious_files)} 个可疑文件\n总计 {total} 个威胁\n\n删除病毒？")
        if choice: self.delete_viruses()
        elif msg_ask("威胁处理", "隔离可疑文件？"): self.quarantine_suspicious()
        elif msg_ask("威胁处理", "查看详情？"): self.show_threat_details()

    def _force_delete(self, filepath):
        """强力删除：普通删除→抢所有权→重启删除"""
        # 1. 普通删除
        try:
            os.remove(filepath)
            return True
        except:
            pass
        # 2. takeown + icacls 抢所有权
        try:
            os.system(f'takeown /f "{filepath}" /a >nul 2>&1')
            os.system(f'icacls "{filepath}" /grant Administrators:F /q >nul 2>&1')
            os.remove(filepath)
            return True
        except:
            pass
        # 3. 重启后删除（终极手段）
        try:
            import ctypes.wintypes as wt
            MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
            ctypes.windll.kernel32.MoveFileExW(filepath, None, MOVEFILE_DELAY_UNTIL_REBOOT)
            return True
        except:
            pass
        return False

    def delete_viruses(self):
        deleted, failed, reboot = 0, 0, 0
        for fi in self.infected_files:
            fp = fi["path"]
            if not os.path.exists(fp):
                deleted += 1
                continue
            result = self._force_delete(fp)
            if result:
                deleted += 1
                # 检查是不是排程到重启了（文件还在=重启删除）
                if os.path.exists(fp):
                    reboot += 1
            else:
                failed += 1
        msg = f"删除完成！\n成功: {deleted} 个"
        if reboot > 0:
            msg += f"\n(其中 {reboot} 个将在重启后删除)"
        if failed > 0:
            msg += f"\n失败: {failed} 个"
        msg_info("结果", msg)

    def quarantine_suspicious(self):
        qd="quarantine"; os.makedirs(qd,exist_ok=True)
        quarantined,failed=0,0
        for fi in self.suspicious_files:
            try:
                if os.path.exists(fi["path"]):
                    ts=datetime.now().strftime("%Y%m%d_%H%M%S"); fn=os.path.basename(fi["path"])
                    qp=os.path.join(qd,f"{ts}_{fn}"); os.rename(fi["path"],qp)
                    with open(qp+".info.json","w",encoding="utf-8") as f: json.dump(fi,f,indent=2,ensure_ascii=False)
                    quarantined+=1
            except Exception as e: failed+=1
        msg_info("结果", f"隔离完成！\n成功隔离: {quarantined} 个可疑文件\n隔离失败: {failed} 个文件")

    def show_threat_details(self):
        all_threats = self.infected_files+self.suspicious_files
        if not all_threats:
            msg_info("详情", "没有发现威胁文件")
            return
        # 在现代界面中用详情窗口显示
        show_threat_details_window(all_threats)

    def scan_processes(self):
        if not self._check_psutil(): return [], "请先安装psutil库: pip install psutil"
        sp=self.process_scanner.scan_running_processes()
        self.suspicious_processes=sp; self.stats["suspicious_processes"]=len(sp)
        return sp, f"发现 {len(sp)} 个可疑进程"

    def _check_psutil(self):
        try: import psutil; return True
        except ImportError:
            if self.is_ui_mode: msg_warn("缺少依赖", "请先安装psutil库: pip install psutil")
            return False

    def kill_all_suspicious_processes(self):
        if not self.suspicious_processes: return True, "没有可疑进程需要结束"
        sc,fc,msgs=0,0,[]
        for proc in self.suspicious_processes:
            success,msg=self.process_scanner.kill_malicious_process(proc['pid'])
            if success: sc+=1; msgs.append(f"✓ 进程 {proc['name']} (PID: {proc['pid']}) 已结束")
            else: fc+=1; msgs.append(f"✗ 进程 {proc['name']} (PID: {proc['pid']}) 结束失败: {msg}")
        return sc>0, f"结束进程完成:\n成功: {sc} 个\n失败: {fc} 个\n\n详细信息:\n"+"\n".join(msgs)


# ==================== 现代 CustomTkinter 界面 ====================

# 全局 UI 状态
ui_root = None
ui_content_frame = None
ui_sidebar_frame = None
ui_status_label = None
ui_alert_label = None
av_instance = None

def _show_alert_banner(message, color="#d93025", score=0):
    """告警：低分→通知条 高分→系统弹窗"""
    # 高危（>80分）：系统通知弹出来，不能错过
    if score > 80:
        try:
            toast = Toast()
            toast.text_fields = ["🚨 PYAntivirus 高危告警", message]
            toaster.show_toast(toast)
        except:
            pass

    # 所有告警都在窗口内显示通知条
    if not ui_content_frame:
        return
    try:
        banner_color = "#b71c1c" if score > 80 else color
        banner = ctk.CTkFrame(ui_content_frame, fg_color=banner_color, corner_radius=6)
        children = ui_content_frame.winfo_children()
        if children:
            banner.pack(fill="x", padx=5, pady=(0, 2), after=children[-1])  # 底部
        else:
            banner.pack(fill="x", padx=5, pady=(2, 0))
        ctk.CTkLabel(banner, text=message, font=ctk.CTkFont(size=12),
                     text_color="white").pack(pady=6, padx=12)
        ui_root.after(5000, banner.destroy)
    except:
        pass

def show_threat_details_window(all_threats):
    """显示威胁详情的独立窗口"""
    detail_win = ctk.CTkToplevel(ui_root)
    detail_win.title("威胁文件详情")
    detail_win.geometry("700x500")
    detail_win.attributes('-topmost', True)

    title_label = ctk.CTkLabel(detail_win, text=f"总计发现 {len(all_threats)} 个威胁文件",
                               font=ctk.CTkFont(size=16, weight="bold"))
    title_label.pack(pady=10)

    textbox = ctk.CTkTextbox(detail_win, wrap="word", font=ctk.CTkFont(size=12))
    textbox.pack(fill="both", expand=True, padx=10, pady=10)

    details = f"已知病毒: {sum(1 for t in all_threats if t['type']=='已知病毒')} 个\n"
    details += f"可疑文件: {sum(1 for t in all_threats if t['type']=='可疑文件')} 个\n\n"

    for i, threat in enumerate(all_threats, 1):
        fn = os.path.basename(threat["path"])
        details += f"{i}. {fn}\n"
        details += f"   类型: {threat['type']}\n"
        details += f"   路径: {threat['path']}\n"
        details += f"   评分: {threat['score']}\n"
        if threat.get("findings"):
            details += f"   发现: {threat['findings'][0]}\n"
            if len(threat["findings"])>1:
                details += f"      还有 {len(threat['findings'])-1} 个发现...\n"
        details += "\n"

    textbox.insert("1.0", details)
    textbox.configure(state="disabled")

    close_btn = ctk.CTkButton(detail_win, text="关闭",
                              command=lambda: detail_win.after(10, detail_win.destroy))
    close_btn.pack(pady=10)


def show_about_dialog():
    """显示关于窗口"""
    about_win = ctk.CTkToplevel(ui_root)
    about_win.title("关于")
    about_win.geometry("500x550")
    about_win.attributes('-topmost', True)

    ctk.CTkLabel(about_win, text="Cmd Antivirus", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=15)
    ctk.CTkLabel(about_win, text="版本: 3.3", font=ctk.CTkFont(size=14)).pack()
    ctk.CTkLabel(about_win, text="作者: _Windows11", font=ctk.CTkFont(size=14)).pack(pady=5)

    about_text = """功能:
• 哈希匹配病毒检测
• 启发式扫描检测未知威胁
• 进程恶意代码扫描
• 文件内容分析
• 行为特征检测
• 隔离和删除威胁文件
• 详细的扫描报告

依赖库:
• customtkinter: 现代图形用户界面
• psutil: 进程和系统信息
• pefile: PE文件分析
• windows-toasts: Windows通知
• watchdog: 文件系统监控

©Copyright _Windows11 All Rights Reserved."""

    textbox = ctk.CTkTextbox(about_win, wrap="word", font=ctk.CTkFont(size=12))
    textbox.pack(fill="both", expand=True, padx=20, pady=10)
    textbox.insert("1.0", about_text)
    textbox.configure(state="disabled")

    ctk.CTkButton(about_win, text="关闭",
                  command=lambda: about_win.after(10, about_win.destroy)).pack(pady=10)


def show_settings_dialog(av):
    """显示设置窗口"""
    settings_win = ctk.CTkToplevel(ui_root)
    settings_win.title("设置")
    settings_win.geometry("500x450")
    settings_win.attributes('-topmost', True)

    ctk.CTkLabel(settings_win, text="软件设置", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=15)

    # 病毒库路径
    ctk.CTkLabel(settings_win, text="病毒库路径:", anchor="w").pack(padx=20, pady=(10,0), fill="x")
    db_path_var = ctk.StringVar(value=av.settings.get("virus_db_path", "virus_hash_lib.json"))
    ctk.CTkEntry(settings_win, textvariable=db_path_var).pack(padx=20, pady=(0,10), fill="x")

    # 默认扫描路径
    ctk.CTkLabel(settings_win, text="默认扫描路径:", anchor="w").pack(padx=20, pady=(10,0), fill="x")
    scan_path_var = ctk.StringVar(value=av.settings.get("default_scan_path", "C:\\"))
    ctk.CTkEntry(settings_win, textvariable=scan_path_var).pack(padx=20, pady=(0,10), fill="x")

    # 自动删除病毒
    auto_delete_var = ctk.BooleanVar(value=av.settings.get("auto_delete", False))
    ctk.CTkCheckBox(settings_win, text="自动删除病毒文件", variable=auto_delete_var).pack(padx=20, pady=5, anchor="w")

    # 自动隔离
    auto_quarantine_var = ctk.BooleanVar(value=av.settings.get("auto_quarantine", False))
    ctk.CTkCheckBox(settings_win, text="自动隔离可疑文件", variable=auto_quarantine_var).pack(padx=20, pady=5, anchor="w")

    # 启发式扫描
    heuristic_var = ctk.BooleanVar(value=av.settings.get("heuristic_enabled", True))
    ctk.CTkCheckBox(settings_win, text="启用启发式扫描", variable=heuristic_var).pack(padx=20, pady=5, anchor="w")

    # 主题选择
    ctk.CTkLabel(settings_win, text="界面主题:", anchor="w").pack(padx=20, pady=(15,0), fill="x")
    theme_var = ctk.StringVar(value=av.settings.get("theme", "system"))
    theme_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
    theme_frame.pack(padx=20, pady=5, fill="x")
    for val, label in [("dark", "🌙 暗色"), ("light", "☀ 亮色"), ("system", "💻 跟随系统")]:
        ctk.CTkRadioButton(theme_frame, text=label, variable=theme_var, value=val).pack(side="left", padx=10)

    # 字体选择
    ctk.CTkLabel(settings_win, text="界面字体:", anchor="w").pack(padx=20, pady=(15,0), fill="x")
    font_var = ctk.StringVar(value=av.settings.get("font", "Microsoft YaHei"))
    font_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
    font_frame.pack(padx=20, pady=5, fill="x")
    fonts = ["Microsoft YaHei", "SimSun", "SimHei", "KaiTi", "FangSong",
             "Courier New", "Minecraft", "Consolas", "Segoe UI", "Arial", "System"]
    font_menu = ctk.CTkOptionMenu(font_frame, values=fonts, variable=font_var, width=180)
    font_menu.pack(side="left", padx=5)

    def save_settings_action():
        av.settings["virus_db_path"] = db_path_var.get()
        av.settings["default_scan_path"] = scan_path_var.get()
        av.settings["auto_delete"] = auto_delete_var.get()
        av.settings["auto_quarantine"] = auto_quarantine_var.get()
        av.settings["heuristic_enabled"] = heuristic_var.get()
        av.settings["theme"] = theme_var.get()
        av.settings["font"] = font_var.get()
        ctk.set_appearance_mode(theme_var.get())
        # 应用字体
        try:
            ctk.set_widget_scaling(1.0)
            ctk.CTkFont._font_family = font_var.get()
        except:
            pass
        success, msg = av.save_settings()
        if success:
            msg_info("成功", "设置已保存\n字体更改需重启生效")
            settings_win.after(10, settings_win.destroy)
        else:
            msg_error("错误", f"保存设置失败: {msg}")

    btn_frame = ctk.CTkFrame(settings_win, fg_color="transparent")
    btn_frame.pack(pady=20)
    ctk.CTkButton(btn_frame, text="保存", command=save_settings_action, width=100).pack(side="left", padx=10)
    ctk.CTkButton(btn_frame, text="取消", command=lambda: settings_win.after(10, settings_win.destroy), width=100, fg_color="gray").pack(side="left", padx=10)


def show_manual_kill_dialog(av):
    """🗡️ 手动杀进程：优先内核驱动，驱动没加载就退回用户态"""
    win = ctk.CTkToplevel(ui_root)
    win.title("手动杀进程")
    win.geometry("540x600")
    win.attributes('-topmost', True)

    ctk.CTkLabel(win, text="🗡️ 手动杀进程",
                 font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))

    # 驱动连接状态
    try:
        from AtivirusKernelIO import IO
        with IO() as kio:
            kio.get_version()
        driver_txt = "🟢 内核驱动已连接 —— 杀进程走内核"
    except Exception:
        driver_txt = "⚪ 内核驱动未连接 —— 杀进程走用户态"
    ctk.CTkLabel(win, text=driver_txt, font=ctk.CTkFont(size=12)).pack(pady=5)

    # 进程下拉列表
    proc_var = ctk.StringVar(value="（点击刷新加载进程列表）")
    proc_menu = ctk.CTkOptionMenu(win, variable=proc_var, width=440,
                                  values=["（点击刷新加载进程列表）"])
    proc_menu.pack(pady=10)

    def refresh_list():
        try:
            import psutil
            procs = sorted(
                ((p.info['pid'], p.info['name'] or '?')
                 for p in psutil.process_iter(['pid', 'name'])),
                key=lambda x: x[0])
            values = [f"{pid}  {name}" for pid, name in procs]
            proc_menu.configure(values=values)
            proc_var.set(values[0] if values else "（无进程）")
        except Exception as e:
            proc_var.set(f"（读取进程失败: {e}）")

    refresh_list()
    ctk.CTkButton(win, text="🔄 刷新列表", command=refresh_list, width=120).pack(pady=5)

    # ===== Ring0 隐藏进程扫描 =====
    hidden_box = ctk.CTkTextbox(win, height=110, font=ctk.CTkFont(size=11))
    hidden_box.pack(padx=20, pady=(5, 5), fill="x")
    hidden_box.insert("1.0", "隐藏进程检测结果会显示在这里")
    hidden_box.configure(state="disabled")

    def scan_hidden():
        """内核 PID 空间扫描 vs 用户态 psutil → 差值 = 隐藏进程"""
        win.configure(cursor="watch")
        try:
            from AtivirusKernelIO import IO
            with IO() as kio:
                kernel_procs = kio.scan_all_processes()
        except Exception as e:
            win.configure(cursor="")
            result_label.configure(text=f"❌ 内核进程扫描失败: {e}", text_color="red")
            return
        user_pids = set()
        try:
            import psutil
            for p in psutil.process_iter(['pid']):
                try:
                    user_pids.add(p.info['pid'])
                except Exception:
                    pass
        except Exception:
            pass
        hidden = [(pid, name) for pid, name in kernel_procs if pid not in user_pids]
        hidden_box.configure(state="normal")
        hidden_box.delete("1.0", "end")
        if hidden:
            for pid, name in hidden:
                hidden_box.insert("end", f"🕵️ 隐藏进程 PID {pid}: {name or '未知'}\n")
            hidden_box.insert("end", f"\n共 {len(hidden)} 个——输入 PID 用上方按钮击杀")
        else:
            hidden_box.insert("end", "✅ 未发现隐藏进程（内核视角与用户态一致）")
        hidden_box.configure(state="disabled")
        win.configure(cursor="")
        result_label.configure(
            text=f"内核进程总数: {len(kernel_procs)}，用户态可见: {len(kernel_procs) - len(hidden)}",
            text_color="gray")

    ctk.CTkButton(win, text="🔍 隐藏进程扫描(Ring0)", command=scan_hidden, width=180).pack(pady=5)

    # 直接输 PID
    ctk.CTkLabel(win, text="或直接输入 PID:", font=ctk.CTkFont(size=12)).pack(pady=(15, 0))
    pid_entry = ctk.CTkEntry(win, width=200, placeholder_text="例如 12345")
    pid_entry.pack(pady=5)

    result_label = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=12), text_color="gray")
    result_label.pack(pady=10)

    def do_kill():
        sel = proc_var.get()
        pid_str = pid_entry.get().strip()
        if not pid_str and sel and sel[0].isdigit():
            pid_str = sel.split()[0]
        if not pid_str.isdigit():
            result_label.configure(text="⚠ 请输入有效 PID", text_color="orange")
            return
        ok, msg = av.process_scanner.kill_malicious_process(int(pid_str))
        result_label.configure(
            text=("✅ " + msg) if ok else ("❌ " + msg),
            text_color="green" if ok else "red")
        refresh_list()

    ctk.CTkButton(win, text="💀 杀进程", command=do_kill,
                  fg_color="#d93025", hover_color="#a52a1f",
                  width=160, height=38,
                  font=ctk.CTkFont(size=13, weight="bold")).pack(pady=10)
    ctk.CTkButton(win, text="关闭", command=win.destroy, width=100,
                  fg_color="gray").pack(pady=5)


def show_train_model_dialog(av):
    """🧠 ML 模型训练：选病毒样本 → 后台训练 100 棵决策树 → 保存模型"""
    win = ctk.CTkToplevel(ui_root)
    win.title("训练 ML 模型")
    win.geometry("560x540")
    win.attributes('-topmost', True)

    ctk.CTkLabel(win, text="🧠 训练 ML 模型",
                 font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
    ctk.CTkLabel(win, text="病毒样本 + 正常文件 → 100 棵树投票 → 保存 ml_model.json",
                 font=ctk.CTkFont(size=12), text_color="gray").pack()

    # 恶意样本目录
    mal_var = ctk.StringVar(value="")
    mal_frame = ctk.CTkFrame(win, fg_color="transparent")
    mal_frame.pack(pady=(15, 5), padx=20, fill="x")
    ctk.CTkLabel(mal_frame, text="🦠 病毒样本文件夹:", font=ctk.CTkFont(size=12),
                 text_color="gray").pack(side="left")
    ctk.CTkEntry(mal_frame, textvariable=mal_var, width=230).pack(side="left", padx=5)

    def browse_mal():
        from tkinter import filedialog
        p = filedialog.askdirectory(title="选择病毒样本文件夹")
        if p:
            mal_var.set(p)

    ctk.CTkButton(mal_frame, text="浏览...", width=70, command=browse_mal).pack(side="left")

    # 正常样本目录（默认 System32）
    ben_var = ctk.StringVar(value="")
    ben_frame = ctk.CTkFrame(win, fg_color="transparent")
    ben_frame.pack(pady=5, padx=20, fill="x")
    ctk.CTkLabel(ben_frame, text="📁 正常文件文件夹:", font=ctk.CTkFont(size=12),
                 text_color="gray").pack(side="left")
    ctk.CTkEntry(ben_frame, textvariable=ben_var, width=230,
                 placeholder_text="留空 = 默认 System32").pack(side="left", padx=5)

    def browse_ben():
        from tkinter import filedialog
        p = filedialog.askdirectory(title="选择正常文件文件夹")
        if p:
            ben_var.set(p)

    ctk.CTkButton(ben_frame, text="浏览...", width=70, command=browse_ben).pack(side="left")

    # 训练日志区
    log_box = ctk.CTkTextbox(win, height=190, font=ctk.CTkFont(size=11))
    log_box.pack(padx=20, pady=10, fill="both", expand=True)

    status_label = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=12), text_color="gray")
    status_label.pack(pady=5)

    def do_train():
        import io
        import contextlib
        if hasattr(sys, '_MEIPASS'):
            # 打包版：sklearn 不在主程序包里，训练走独立的 ml_trainer.exe
            status_label.configure(
                text="打包版训练请用独立工具:\nml_trainer.exe --malware <病毒样本目录> --benign <正常目录> --output <模型路径>",
                text_color="orange")
            return
        mal = mal_var.get().strip()
        if not mal:
            status_label.configure(text="⚠ 请先选择病毒样本文件夹", text_color="orange")
            return
        ben = ben_var.get().strip() or None
        win.configure(cursor="watch")
        status_label.configure(text="⏳ 训练中（提取特征很耗时）...", text_color="orange")

        def run():
            ms = av.ml_scanner or MLScanner()
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    # 打包后存 exe 旁边（_MEIPASS 是临时解压目录，存那里重启就丢）
                    save_path = (os.path.join(os.path.dirname(sys.executable), "ml_model.json")
                                 if hasattr(sys, '_MEIPASS') else None)
                    ok, msg = ms.auto_train(mal, ben, save_path=save_path)
            except Exception as e:
                ok, msg = False, f"训练异常: {e}"
            if ok:
                av.ml_scanner = ms  # 把新模型挂回引擎
            ui_root.after(0, lambda: finish(ok, msg, buf))

        def finish(ok, msg, buf):
            win.configure(cursor="")
            log_box.insert("end", buf.getvalue())
            log_box.see("end")
            status_label.configure(
                text=("✅ " + msg) if ok else ("❌ " + msg),
                text_color="green" if ok else "red")

        threading.Thread(target=run, daemon=True).start()

    ctk.CTkButton(win, text="🚀 开始训练", command=do_train,
                  font=ctk.CTkFont(size=14, weight="bold"), height=40,
                  fg_color="#188038", hover_color="#0d6522").pack(pady=10)
    ctk.CTkButton(win, text="关闭", command=win.destroy, width=100,
                  fg_color="gray").pack(pady=5)


def show_scan_history_ui():
    """显示扫描历史（在内容区）"""
    clear_content_area()

    ctk.CTkLabel(ui_content_frame, text="📋 扫描历史记录",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(pady=15)

    history_dir = "scan_reports"
    if not os.path.exists(history_dir):
        ctk.CTkLabel(ui_content_frame, text="暂无扫描历史记录",
                     font=ctk.CTkFont(size=14)).pack(pady=50)
        return

    report_files = [f for f in os.listdir(history_dir) if f.endswith('.json')]
    if not report_files:
        ctk.CTkLabel(ui_content_frame, text="暂无扫描历史记录",
                     font=ctk.CTkFont(size=14)).pack(pady=50)
        return

    report_files.sort(reverse=True)

    textbox = ctk.CTkTextbox(ui_content_frame, wrap="word", font=ctk.CTkFont(size=12))
    textbox.pack(fill="both", expand=True, padx=20, pady=10)

    for i, rf in enumerate(report_files[:20], 1):
        fp = os.path.join(history_dir, rf)
        try:
            with open(fp, 'r', encoding='utf-8') as f: report = json.load(f)
            st = report.get('scan_time', '未知时间')
            sf = report.get('scanned_files', 0)
            inf = report.get('infected_files', 0)
            sus = report.get('suspicious_files', 0)
            textbox.insert("end", f"{i}. {st}\n")
            textbox.insert("end", f"   扫描文件: {sf} 个  病毒: {inf} 个  可疑: {sus} 个\n\n")
        except:
            textbox.insert("end", f"{i}. {rf} (文件损坏)\n\n")

    textbox.configure(state="disabled")


def clear_content_area():
    """清空内容区域"""
    for widget in ui_content_frame.winfo_children():
        widget.destroy()


def update_status(text):
    """更新状态栏"""
    if ui_status_label:
        ui_status_label.configure(text=text)


def run_scan_thread(av, scan_path, scan_mode):
    """在后台线程中运行扫描，通过after更新UI"""
    av.scan_running = True
    av.scan_canceled = False
    av.stats = {"scanned": 0, "infected": 0, "suspicious": 0, "suspicious_processes": 0}
    av.infected_files = []
    av.suspicious_files = []

    # 显示扫描中界面
    clear_content_area()
    ctk.CTkLabel(ui_content_frame, text=f"🔍 正在{scan_mode}...",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(pady=15)
    ctk.CTkLabel(ui_content_frame, text=f"扫描路径: {scan_path}",
                 font=ctk.CTkFont(size=12)).pack(pady=5)

    progress_bar = ctk.CTkProgressBar(ui_content_frame)
    progress_bar.pack(padx=40, pady=10, fill="x")
    progress_bar.set(0)

    stats_label = ctk.CTkLabel(ui_content_frame, text="已扫描: 0 个文件\n病毒: 0  可疑: 0",
                               font=ctk.CTkFont(size=14))
    stats_label.pack(pady=10)

    cancel_btn = ctk.CTkButton(ui_content_frame, text="取消扫描", fg_color="red",
                               command=lambda: setattr(av, 'scan_canceled', True))
    cancel_btn.pack(pady=5)

    def do_scan():
        try:
            results = av.scan_directory(scan_path)
        except Exception as e:
            ui_root.after(0, lambda: msg_error("错误", f"扫描过程中出错: {str(e)}"))
        finally:
            av.scan_running = False

    scan_thread = threading.Thread(target=do_scan)
    scan_thread.daemon = True
    scan_thread.start()

    def update_ui():
        if av.scan_running:
            progress_bar.set(av.stats["scanned"] / max(av.stats["scanned"] + 100, 1) * 0.9)
            stats_label.configure(
                text=f"已扫描: {av.stats['scanned']} 个文件\n病毒: {av.stats['infected']}  可疑: {av.stats['suspicious']}")
            ui_root.after(100, update_ui)
        else:
            # 扫描完成
            progress_bar.set(1.0)
            show_scan_results(av, scan_path, scan_mode)

    ui_root.after(100, update_ui)


def show_scan_results(av, scan_path, scan_mode):
    """显示扫描结果"""
    clear_content_area()

    ctk.CTkLabel(ui_content_frame, text="✅ 扫描完成!",
                 font=ctk.CTkFont(size=22, weight="bold")).pack(pady=15)

    # 结果统计
    stats_frame = ctk.CTkFrame(ui_content_frame)
    stats_frame.pack(padx=20, pady=10, fill="x")

    stats_data = [
        ("扫描文件数", str(av.stats['scanned'])),
        ("发现病毒", str(av.stats['infected'])),
        ("可疑文件", str(av.stats['suspicious'])),
        ("总计威胁", str(av.stats['infected'] + av.stats['suspicious'])),
    ]
    for label, value in stats_data:
        row = ctk.CTkFrame(stats_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=3)
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13), width=120).pack(side="left")
        ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="red" if "病毒" in label or "威胁" in label else None).pack(side="left")

    # 操作按钮
    btn_frame = ctk.CTkFrame(ui_content_frame, fg_color="transparent")
    btn_frame.pack(pady=15)

    if av.stats['infected'] > 0 or av.stats['suspicious'] > 0:
        ctk.CTkButton(btn_frame, text="🗑 处理威胁",
                      command=lambda: av._show_threat_action_ui(),
                      fg_color="#d93025", hover_color="#b71c1c").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="📋 查看详情",
                      command=lambda: show_threat_details_window(av.infected_files+av.suspicious_files)).pack(side="left", padx=5)

    def save_report():
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile=f"scan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if file_path:
            av.generate_report(av.infected_files+av.suspicious_files, file_path)
            msg_info("保存成功", f"报告已保存到:\n{file_path}")

    ctk.CTkButton(btn_frame, text="💾 保存报告", command=save_report).pack(side="left", padx=5)
    ctk.CTkButton(btn_frame, text="🔄 返回主页", command=show_main_page).pack(side="left", padx=5)

    if av.stats['infected'] == 0 and av.stats['suspicious'] == 0:
        ctk.CTkLabel(ui_content_frame, text="🎉 恭喜！未发现威胁文件。",
                     font=ctk.CTkFont(size=16), text_color="green").pack(pady=20)


def show_process_scan_ui(av):
    """显示进程扫描界面"""
    clear_content_area()

    ctk.CTkLabel(ui_content_frame, text="🔍 进程扫描",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(pady=15)

    if not av._check_psutil():
        return

    ctk.CTkLabel(ui_content_frame, text="正在扫描运行中的进程...",
                 font=ctk.CTkFont(size=14)).pack(pady=10)

    progress_bar = ctk.CTkProgressBar(ui_content_frame)
    progress_bar.pack(padx=40, pady=10, fill="x")
    progress_bar.configure(mode="indeterminate")
    progress_bar.start()

    status_label = ctk.CTkLabel(ui_content_frame, text="请稍候...", font=ctk.CTkFont(size=12))
    status_label.pack()

    def do_scan():
        sp, msg = av.scan_processes()
        ui_root.after(0, lambda: show_process_results(av, sp, msg))

    scan_thread = threading.Thread(target=do_scan)
    scan_thread.daemon = True
    scan_thread.start()


def show_process_results(av, suspicious_processes, result_msg):
    """显示进程扫描结果"""
    clear_content_area()

    ctk.CTkLabel(ui_content_frame, text="进程扫描结果",
                 font=ctk.CTkFont(size=20, weight="bold")).pack(pady=15)

    if not suspicious_processes:
        ctk.CTkLabel(ui_content_frame, text="✅ 未发现可疑进程。",
                     font=ctk.CTkFont(size=16), text_color="green").pack(pady=30)
        ctk.CTkButton(ui_content_frame, text="返回主页", command=show_main_page).pack(pady=10)
        return

    ctk.CTkLabel(ui_content_frame, text=f"⚠️ 发现 {len(suspicious_processes)} 个可疑进程",
                 font=ctk.CTkFont(size=16), text_color="orange").pack(pady=5)

    textbox = ctk.CTkTextbox(ui_content_frame, wrap="word", font=ctk.CTkFont(size=11), height=200)
    textbox.pack(fill="x", padx=20, pady=10)

    for i, proc in enumerate(suspicious_processes[:20], 1):
        textbox.insert("end", f"{i}. {proc['name']} (PID: {proc['pid']})\n")
        textbox.insert("end", f"   路径: {proc['exe_path'] or '未知'}\n")
        if proc.get('findings'):
            textbox.insert("end", f"   发现: {proc['findings'][0]}\n")
        textbox.insert("end", "\n")
    textbox.configure(state="disabled")

    btn_frame = ctk.CTkFrame(ui_content_frame, fg_color="transparent")
    btn_frame.pack(pady=10)

    def kill_procs():
        success, msg = av.kill_all_suspicious_processes()
        msg_info("结束进程结果", msg)

    def save_proc_report():
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile=f"proc_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "suspicious_processes": suspicious_processes}, f, indent=2, ensure_ascii=False)
            msg_info("保存成功", f"报告已保存到:\n{file_path}")

    ctk.CTkButton(btn_frame, text="💾 保存报告", command=save_proc_report).pack(side="left", padx=5)
    ctk.CTkButton(btn_frame, text="🔄 返回主页", command=show_main_page).pack(side="left", padx=5)


def show_main_page():
    """显示主页——扫描仪表盘"""
    clear_content_area()

    # 标题
    ctk.CTkLabel(ui_content_frame, text="🛡️ PYAntivirus",
                 font=ctk.CTkFont(size=28, weight="bold")).pack(pady=(30,5))
    ctk.CTkLabel(ui_content_frame, text="v3.3 · 7层智能检测引擎",
                 font=ctk.CTkFont(size=13), text_color=("gray40", "gray70")).pack()

    # ====== 大大的扫描按钮 ======
    btn_frame = ctk.CTkFrame(ui_content_frame, fg_color="transparent")
    btn_frame.pack(pady=30)

    av = av_instance  # 用全局实例

    # 快速扫描
    quick_btn = ctk.CTkButton(btn_frame, text="⚡ 快速扫描\nSystem32 关键区域",
                              font=ctk.CTkFont(size=16, weight="bold"),
                              width=200, height=80, corner_radius=12,
                              fg_color="#1a73e8", hover_color="#1557b0",
                              command=lambda: run_scan_thread(av, "C:\\Windows\\System32", "快速扫描"))
    quick_btn.pack(side="left", padx=10, pady=10)

    # 全盘扫描
    full_btn = ctk.CTkButton(btn_frame, text="💿 全盘扫描\n整个 C 盘",
                             font=ctk.CTkFont(size=16, weight="bold"),
                             width=200, height=80, corner_radius=12,
                             fg_color="#e37400", hover_color="#b85d00",
                             command=lambda: run_scan_thread(av, "C:\\", "全盘扫描"))
    full_btn.pack(side="left", padx=10, pady=10)

    # 自定义扫描
    custom_btn = ctk.CTkButton(btn_frame, text="📁 自定义扫描\n选择文件夹",
                               font=ctk.CTkFont(size=16, weight="bold"),
                               width=200, height=80, corner_radius=12,
                               fg_color="#188038", hover_color="#0d6522",
                               command=lambda: custom_scan_dialog(av))
    custom_btn.pack(side="left", padx=10, pady=10)

    # ====== 状态信息 ======
    info_frame = ctk.CTkFrame(ui_content_frame)
    info_frame.pack(padx=40, pady=20, fill="x")

    ctk.CTkLabel(info_frame, text="🛡️ 实时文件监控：运行中  |  🗄️ 病毒库：已加载  |  🔐 数字签名验证：开启",
                 font=ctk.CTkFont(size=12), text_color=("gray40", "gray70")).pack(pady=10)

    features = [
        "✅ 哈希匹配 · ✅ 启发式扫描 · ✅ PE深度分析 · ✅ YARA规则引擎",
        "✅ 数字签名验证 · ✅ 勒索软件检测 · ✅ 反虚拟机检测 · ✅ 进程注入检测",
    ]
    for feat in features:
        ctk.CTkLabel(info_frame, text=feat, font=ctk.CTkFont(size=11), text_color=("gray40", "gray70")).pack(pady=2)


def build_ui(av):
    """构建主窗口界面"""
    global ui_root, ui_content_frame, ui_sidebar_frame, ui_status_label, av_instance
    av_instance = av

    ui_root = ctk.CTk()
    ui_root.title("PYAntivirus v3.3 — 现代界面")
    ui_root.geometry("900x600")
    ui_root.minsize(800, 500)

    # 窗口图标
    try:
        icon = resource_path("icon.ico")
        ui_root.iconbitmap(icon)  # 底层 tk 方法
    except Exception:
        pass

    # ====== 左侧边栏 ======
    ui_sidebar_frame = ctk.CTkFrame(ui_root, width=180, corner_radius=0,
                                     fg_color=("#e8e8e8", "#1a1a1a"))  # 浅/暗区分
    ui_sidebar_frame.pack(side="left", fill="y")
    ui_sidebar_frame.pack_propagate(False)

    # Logo
    ctk.CTkLabel(ui_sidebar_frame, text="PYAntivirus",
                 text_color=("gray10", "gray90"),
                 font=ctk.CTkFont(size=16, weight="bold")).pack(pady=20)

    # 分隔线
    ctk.CTkFrame(ui_sidebar_frame, height=2, fg_color="gray").pack(fill="x", padx=15, pady=5)

    # MBR/EFI 工具函数
    def run_mbr_backup():
        os.system("fix_efi_mbr_aft10.exe --backup")
        msg_info("MBR/EFI备份", "备份命令已执行！")

    def run_mbr_repair():
        from tkinter import messagebox
        if messagebox.askyesno("确认", "修复MBR/EFI有风险！\n\n确定要继续吗？"):
            os.system("fix_efi_mbr_aft10.exe --repair")
            msg_info("MBR/EFI修复", "修复命令已执行！")

    # 导航按钮（扫描在主页仪表盘，侧边栏只放工具）
    nav_buttons = [
        ("🏠 主页", show_main_page),
        ("📋 扫描历史", show_scan_history_ui),
        ("🗡️ 手动杀进程", lambda: show_manual_kill_dialog(av)),
        ("🧠 训练模型", lambda: show_train_model_dialog(av)),
        ("💾 备份MBR/EFI", run_mbr_backup),
        ("🔧 修复MBR/EFI", run_mbr_repair),
        ("⚙️ 设置", lambda: show_settings_dialog(av)),
        ("ℹ️ 关于", show_about_dialog),
    ]

    for text, cmd in nav_buttons:
        btn = ctk.CTkButton(ui_sidebar_frame, text=text, command=cmd,
                           anchor="w", height=38, fg_color="transparent",
                           text_color=("gray10", "gray90"),
                           hover_color=("gray75", "gray25"))
        btn.pack(padx=10, pady=3, fill="x")

    # 底部——最小化到托盘按钮
    ctk.CTkFrame(ui_sidebar_frame, height=2, fg_color="gray").pack(fill="x", padx=15, pady=5, side="bottom")

    def hide_to_tray():
        """隐藏窗口到系统托盘（不退出程序）"""
        ui_root.withdraw()  # 隐藏窗口，后台继续运行

    ctk.CTkButton(ui_sidebar_frame, text="🔽 最小化到托盘", fg_color="transparent",
                  text_color=("gray10", "gray90"),
                  hover_color=("gray75", "gray25"),
                  command=hide_to_tray,
                  height=35).pack(padx=10, pady=5, fill="x", side="bottom")

    # 真正的退出按钮（红色）
    def quit_app():
        """完全退出程序"""
        ui_root.destroy()
        os._exit(0)

    ctk.CTkButton(ui_sidebar_frame, text="❌ 完全退出", fg_color="transparent",
                  text_color=("gray10", "gray90"),
                  hover_color="#8b0000", command=quit_app,
                  height=35).pack(padx=10, pady=10, fill="x", side="bottom")

    # ====== 右侧主内容区 ======
    main_frame = ctk.CTkFrame(ui_root, fg_color="transparent")
    main_frame.pack(side="right", fill="both", expand=True)

    # 内容区域
    ui_content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
    ui_content_frame.pack(fill="both", expand=True, padx=10, pady=10)

    # 状态栏
    status_bar = ctk.CTkFrame(main_frame, height=30, fg_color=("gray85", "gray17"))
    status_bar.pack(side="bottom", fill="x")
    status_bar.pack_propagate(False)

    ui_status_label = ctk.CTkLabel(status_bar, text="就绪", font=ctk.CTkFont(size=11),
                                   text_color=("gray40", "gray70"))
    ui_status_label.pack(side="left", padx=10)

    # 告警计数标签
    ui_alert_label = ctk.CTkLabel(status_bar, text="", font=ctk.CTkFont(size=11, weight="bold"),
                                  text_color="orange")
    ui_alert_label.pack(side="left", padx=5)

    ctk.CTkLabel(status_bar, text=f"© _Windows11",
                 font=ctk.CTkFont(size=10), text_color=("gray40", "gray70")).pack(side="right", padx=10)

    # 显示主页
    show_main_page()

    # 点窗口 X 按钮 = 缩到托盘，不退出
    ui_root.protocol("WM_DELETE_WINDOW", hide_to_tray)

    return ui_root


def custom_scan_dialog(av):
    """自定义扫描 - 选择文件夹"""
    folder = filedialog.askdirectory(title="请选择要扫描的文件夹")
    if folder:
        run_scan_thread(av, folder, "自定义扫描")


# ==================== 主入口 ====================

def ui_mode(args):
    """UI模式主函数 - 现代界面版"""
    global main_window, started_ui_mode, av_instance
    main_window = 1

    av = AVEngine(enable_heuristic=not (args and args.no_heuristic))
    av.is_ui_mode = True
    av.load_settings()
    # 加载保存的主题
    saved_theme = av.settings.get("theme", "system")
    ctk.set_appearance_mode(saved_theme)

    # 加载自定义字体
    saved_font = av.settings.get("font", "")
    if saved_font == "Minecraft":
        try:
            import ctypes
            ctypes.windll.gdi32.AddFontResourceW(resource_path("Minecraft.ttf"))
        except:
            pass

    av.load_virus_db()
    av_instance = av

    if started_ui_mode == 0:
        started_ui_mode = 1

        # 后台托盘
        tray_av = AVEngine(enable_heuristic=not (args and args.no_heuristic))
        tray_av.is_ui_mode = False
        tray_av.load_settings()
        tray_av.load_virus_db()

        tray_manager = SystemTrayManager(tray_av)
        def run_tray():
            tray_manager.run_in_tray()
        tray_thread = threading.Thread(target=run_tray)
        tray_thread.daemon = True
        tray_thread.start()

        # 后台监控
        def run_monitor():
            mon_av = AVEngine(enable_heuristic=not (args and args.no_heuristic))
            mon_av.load_virus_db()
            start_monitor_mode("C:\\", mon_av)
        monitor_thread = threading.Thread(target=run_monitor)
        monitor_thread.daemon = True
        monitor_thread.start()

        # === 后台自动进程扫描（每5分钟一次）===
        def auto_process_scanner():
            """后台定时扫描进程，发现可疑用托盘气泡通知"""
            ps = ProcessScanner()
            while True:
                time.sleep(300)  # 每5分钟扫一次
                try:
                    suspicious = ps.scan_running_processes()
                    if suspicious:
                        names = ', '.join(p['name'] for p in suspicious[:3])
                        msg = f"⚠ 发现 {len(suspicious)} 个可疑进程: {names}"
                        # 窗口内通知条，不弹窗
                        if ui_root and ui_content_frame:
                            ui_root.after(0, lambda: _show_alert_banner(msg, "#d93025"))
                        if av_instance:
                            av_instance.suspicious_processes = suspicious
                            av_instance.stats["suspicious_processes"] = len(suspicious)
                except:
                    pass

        proc_scanner_thread = threading.Thread(target=auto_process_scanner)
        proc_scanner_thread.daemon = True
        proc_scanner_thread.start()

    # 构建并运行现代界面
    app = build_ui(av)
    app.mainloop()


def main():
    parser = argparse.ArgumentParser(description="Enhanced Command Antivirus")
    parser.add_argument("-p", "--path", default="C:\\", help="扫描路径")
    parser.add_argument("-o", "--output", default="scan_report.json", help="报告文件名")
    parser.add_argument("-ui", "--ui", action="store_true", help="使用GUI界面")
    parser.add_argument("--no-heuristic", action="store_true", help="禁用启发式扫描")
    parser.add_argument("--scan-processes", action="store_true", help="扫描运行中的进程")
    parser.add_argument("--monitor", metavar="PATH", help="监控指定目录，自动扫描新文件")
    parser.add_argument("--monitor-delay", type=int, default=2, help="监控模式下的扫描延迟（秒）")
    args = parser.parse_args()

    if args.monitor:
        av = AVEngine(enable_heuristic=not args.no_heuristic)
        av.is_ui_mode = False
        av.load_virus_db()
        start_monitor_mode(args.monitor, av)
        return

    # 双击启动 → 直接进入现代界面（不需要 -ui 参数）
    # 只有明确 --scan-processes 且没 -ui 时走命令行
    if not args.ui and args.scan_processes:
        av = AVEngine(enable_heuristic=not args.no_heuristic)
        av.load_virus_db()
        suspicious_processes, result_msg = av.scan_processes()
        print(f"\n[+] {result_msg}")
        if suspicious_processes:
            response = input("\n是否要结束这些可疑进程？(y/n): ")
            if response.lower() == 'y':
                success, message = av.kill_all_suspicious_processes()
                print(f"\n{message}")
        return

    # 默认：直接启动现代界面
    ui_mode(args)


if __name__ == "__main__":
    # ====== 自保护：启动时检查完整性 ======
    tampered = verify_integrity()
    if tampered:
        msg = "🚨 检测到关键文件被篡改！\n\n"
        for fname, expected, actual in tampered:
            msg += f"• {fname}\n  期望: {expected}... → 实际: {actual}...\n"
        msg += "\n程序可能已被病毒感染，建议重新安装！"
        # 用 messagebox 警告（如果可用）
        try:
            import tkinter.messagebox as mb
            mb.showerror("PYAntivirus 自保护", msg)
        except:
            print(msg)
        # 不阻止启动，但严重警告

    # ====== 权限提升：优先 TI → 管理员 ======
    # 检查是否已经在 NSudo 下运行（避免无限循环）
    if "--ti" not in sys.argv:
        nsudo = resource_path("NSudo.exe")
        if os.path.exists(nsudo):
            # 有 NSudo → 直接 TI 权限启动
            args_str = " ".join(f'"{a}"' for a in sys.argv)
            os.system(f'"{nsudo}" -U:T -P:E -Wait "{sys.executable}" --ti {args_str}')
            sys.exit()
        elif not ctypes.windll.shell32.IsUserAnAdmin():
            # 没 NSudo → 退而求其次，管理员权限
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
            sys.exit()

    try: import pefile
    except ImportError as e:
        print(f"[!] 缺少依赖库: {e}")
        sys.exit(1)
    try: import psutil
    except ImportError:
        print("[!] 缺少psutil库，进程扫描功能将不可用")

    main()
