#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行杀毒软件 - 增强版
修复设置问题，增加完整的功能
"""
# 添加到已有的import部分
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
import easygui as eg
from datetime import datetime

from win32api import GetCurrentProcess
from windows_toasts import Toast, WindowsToaster
from collections import Counter
import math
import struct
import binascii
import psutil
import ctypes
from collections import Counter
# 在文件开头的import区域添加
import time
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ctypes import wintypes
_main_ = 1
started_ui_mode = 0
main_window = 0
# 加载 kernel32.dll
kernel32 = ctypes.WinDLL('kernel32.dll')
TerminateProcess = kernel32.TerminateProcess
GetCurrentProcess = kernel32.GetCurrentProcess

toaster = WindowsToaster("Antivirus")


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
        """创建系统托盘图标和菜单"""
        try:
            # 尝试从ICO文件加载图标
            image = Image.open("icon.ico")

            # 确保图标尺寸合适（通常16x16或32x32）
            if image.size[0] > 64 or image.size[1] > 64:
                image = image.resize((32, 32), Image.Resampling.LANCZOS)

        except FileNotFoundError:
            # 如果找不到ICO文件，创建一个简单的默认图标
            print("[!] 找不到icon.ico文件，使用默认图标")
            image = self._create_default_icon()
        except Exception as e:
            print(f"[!] 加载图标失败: {e}")
            image = self._create_default_icon()

        # 创建托盘菜单
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

        # 创建托盘图标
        self.tray_icon = pystray.Icon(
            "antivirus_tray",
            image,  # 现在传递的是PIL图像对象
            "命令行杀毒软件 (后台运行中)",
            menu
        )

    def _create_default_icon(self):
        """创建默认图标（红色盾牌）"""
        # 创建一个64x64的图像
        image = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)

        # 绘制红色盾牌
        draw.rectangle([16, 16, 48, 48], fill=(220, 50, 50), outline=(180, 30, 30), width=3)

        # 绘制白色"V"（表示病毒防护）
        draw.line([24, 32, 32, 40], fill=(255, 255, 255), width=3)
        draw.line([32, 40, 40, 32], fill=(255, 255, 255), width=3)

        return image

    def show_main_window(self, icon, item):
        """显示主界面"""
        global main_window
        main_window = 1
        ui_mode()

    def show_status(self, icon, item):
        """显示当前扫描状态"""
        status_msg = (f"扫描状态\n"
                      f"扫描文件: {self.av.stats.get('scanned', 0)}\n"
                      f"发现病毒: {self.av.stats.get('infected', 0)}\n"
                      f"可疑文件: {self.av.stats.get('suspicious', 0)}\n"
                      f"监控状态: {'运行中' if self.monitoring else '已停止'}")
        eg.msgbox(status_msg, "杀毒软件状态")

    def toggle_monitoring(self, icon, item):
        """切换监控状态"""
        if self.monitoring:
            self.stop_monitoring()
            item.text = "启动监控"
        else:
            self.start_monitoring()
            item.text = "暂停监控"

    def open_settings(self, icon, item):
        """打开设置"""
        # 调用现有的设置功能
        show_settings(self.av)

    def show_about(self, icon, item):
        """显示关于信息"""
        show_about()
    '''
    def quit_program(self, icon, item):
        global _main_
        """退出程序"""
        if self.monitoring:
            self.stop_monitoring()
        self.tray_icon.stop()
        _main_ = 0
        os.system("taskkill /f /im Command antivirus.exe")
        #sys.exit(0)
        # TerminateProcess(GetCurrentProcess(), 0)
    '''

    def quit_program(self, icon, item):
        """退出程序"""
        global _main_
        if self.monitoring:
            self.stop_monitoring()

        if self.tray_icon:
            self.tray_icon.stop()

        _main_ = 0

        # 保存设置等清理工作
        try:
            if hasattr(self, 'av') and self.av:
                self.av.save_settings()
        except:
            pass

        # 强制退出Python进程
        import os
        os._exit(0)
    def start_monitoring(self):
        """启动后台监控"""
        if not self.monitor_paths:
            # 默认监控用户下载目录
            default_path = os.path.join(os.path.expanduser("~"), "Downloads")
            self.monitor_paths = [default_path]

        if not self.monitoring:
            self.monitoring = True
            self.monitor_thread = threading.Thread(target=self._run_monitoring)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            print("[*] 后台监控已启动")

    def _run_monitoring(self):
        """运行监控的主循环"""
        # 这里可以调用您之前设置的监控功能
        # 例如：start_monitor_mode 或 FullSystemMonitor
        print(f"[*] 开始监控目录: {self.monitor_paths}")
        # 监控逻辑实现...

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        print("[*] 后台监控已停止")

    def run_in_tray(self):
        """在系统托盘中运行程序"""
        self.create_tray_icon()

        # 启动后台监控
        self.start_monitoring()

        # 运行系统托盘图标
        self.tray_icon.run()

class AutoScanHandler(FileSystemEventHandler):
    """文件系统事件处理器，用于自动扫描新文件"""

    def __init__(self, antivirus_instance, scan_delay=2):
        """
        参数:
            antivirus_instance: SimpleAntivirus实例
            scan_delay: 文件创建后等待的秒数（确保文件完全写入）
        """
        super().__init__()
        self.av = antivirus_instance
        self.scan_delay = scan_delay
        self.file_queue = []
        self.lock = threading.Lock()

    def on_created(self, event):
        """当有新文件或目录创建时触发"""
        if not event.is_directory:
            file_path = event.src_path
            print(f"[监控] 检测到新文件: {file_path}")

            # 将文件加入队列，延迟扫描
            with self.lock:
                self.file_queue.append(file_path)

            # 启动扫描线程
            scan_thread = threading.Thread(target=self._delayed_scan, args=(file_path,))
            scan_thread.daemon = True
            scan_thread.start()

    def on_modified(self, event):
        """当文件被修改时触发"""
        if not event.is_directory:
            file_path = event.src_path
            print(f"[监控] 检测到文件被修改: {file_path}")

            # 可以在这里添加对修改文件的扫描逻辑
            # 例如，扫描可能被注入恶意代码的已存在文件
            pass

    def _delayed_scan(self, file_path):
        """延迟扫描，确保文件已完全写入"""
        time.sleep(self.scan_delay)

        if not os.path.exists(file_path):
            print(f"[监控] 文件已不存在，跳过扫描: {file_path}")
            return

        print(f"[监控] 开始扫描文件: {file_path}")

        try:
            # 调用现有的扫描功能
            scan_type, virus_hash, score, findings, file_hash = self.av.scan_file(file_path, "md5")

            if scan_type == "hash":
                print(f"[!] 发现病毒: {file_path}")
                self.av.stats["infected"] += 1
                self.av.infected_files.append({
                    "path": file_path,
                    "type": "已知病毒",
                    "hash": virus_hash,
                    "score": score,
                    "findings": findings
                })
                self._send_alert_notification(file_path, "病毒", score)

            elif scan_type == "heuristic":
                print(f"[!] 发现可疑文件: {file_path} (评分: {score})")
                self.av.stats["suspicious"] += 1
                self.av.suspicious_files.append({
                    "path": file_path,
                    "type": "可疑文件",
                    "hash": file_hash,
                    "score": score,
                    "findings": findings
                })
                self._send_alert_notification(file_path, "可疑文件", score)

            else:
                print(f"[监控] 文件安全: {file_path}")

        except Exception as e:
            print(f"[监控] 扫描文件失败 {file_path}: {e}")

    def _send_alert_notification(self, file_path, threat_type, score):
        """发送威胁警报通知"""
        filename = os.path.basename(file_path)
        toast = Toast()
        toast.text_fields = [
            f"⚠️ 发现{threat_type}",
            f"文件: {filename}\n"
            f"路径: {os.path.dirname(file_path)}\n"
            f"威胁评分: {score}\n"
            f"时间: {datetime.now().strftime('%H:%M:%S')}"
        ]

        # 可以在这里添加点击通知后的处理逻辑
        toaster.show_toast(toast)


def start_monitor_mode(monitor_path, antivirus_instance):
    """
    启动目录监控模式

    参数:
        monitor_path: 要监控的目录路径
        antivirus_instance: SimpleAntivirus实例
    """
    if not os.path.exists(monitor_path):
        print(f"[!] 监控路径不存在: {monitor_path}")
        return False

    print(f"[*] 启动文件监控模式")
    print(f"[*] 监控目录: {monitor_path}")
    print(f"[*] 当有新文件出现时会自动扫描")
    print(f"[*] 按 Ctrl+C 停止监控\n")

    # 创建事件处理器和观察者
    event_handler = AutoScanHandler(antivirus_instance)
    observer = Observer()
    observer.schedule(event_handler, monitor_path, recursive=True)

    # 启动监控
    observer.start()

    try:
        # 保持主线程运行
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
        # 可疑进程名称模式
        self.suspicious_process_names = [
            r'(?i)(svchost.*exe)',
            r'(?i)(lsass.*exe)',
            r'(?i)(csrss.*exe)',
            r'(?i)(smss.*exe)',
            r'(?i)(winlogon.*exe)',
            r'(?i)(services.*exe)',
            r'(?i)(explorer.*exe)',
            r'(?i)(rundll32.*exe)',
            r'(?i)(wscript.*exe)',
            r'(?i)(cscript.*exe)',
            r'(?i)(powershell.*exe)',
            r'(?i)(cmd.*exe)',
        ]

        # 可疑进程路径模式
        self.suspicious_process_paths = [
            r'(?i)(temp\\|tmp\\)',
            r'(?i)(appdata\\local\\temp\\)',
            r'(?i)(windows\\temp\\)',
            r'(?i)(users\\.*\\appdata\\local\\temp\\)',
        ]

        # 系统进程白名单
        self.system_process_whitelist = [
            'System',
            'System Idle Process',
            'Registry',
            'smss.exe',
            'csrss.exe',
            'wininit.exe',
            'services.exe',
            'lsass.exe',
            'svchost.exe',
            'taskhost.exe',
            'dwm.exe',
            'explorer.exe',
            'conhost.exe',
            'spoolsv.exe',
        ]

        # 常见挖矿进程特征
        self.mining_process_patterns = [
            r'(?i)(xmrig|ccminer|ethminer|claymore|nicehash|miner)',
            r'(?i)(crypto.*miner|bitcoin.*miner)',
        ]

        # 可疑命令行参数
        self.suspicious_cmdline_patterns = [
            r'(?i)(-o\s+.*pool.*)',
            r'(?i)(--url\s+.*pool.*)',
            r'(?i)(-u\s+.*wallet.*)',
            r'(?i)(-p\s+.*x)',
            r'(?i)(--user\s+.*wallet.*)',
            r'(?i)(--pass\s+.*x)',
            r'(?i)(stratum\+tcp://)',
            r'(?i)(-k\s+--donate-level)',
        ]

    def scan_running_processes(self):
        """扫描所有运行中的进程"""
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

                    # 检查进程
                    is_suspicious, findings = self._analyze_process(pid, name, exe_path, cmdline, username)

                    if is_suspicious:
                        suspicious_processes.append({
                            'pid': pid,
                            'name': name,
                            'exe_path': exe_path,
                            'cmdline': cmdline,
                            'username': username,
                            'findings': findings
                        })

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
                except Exception as e:
                    continue

        except Exception as e:
            print(f"[!] 扫描进程时出错: {e}")

        return suspicious_processes

    def _analyze_process(self, pid, name, exe_path, cmdline, username):
        """分析单个进程"""
        findings = []
        score = 0

        # 1. 检查进程名
        name_score, name_findings = self._check_process_name(name)
        score += name_score
        findings.extend(name_findings)

        # 2. 检查进程路径
        path_score, path_findings = self._check_process_path(exe_path)
        score += path_score
        findings.extend(path_findings)

        # 3. 检查命令行参数
        cmdline_score, cmdline_findings = self._check_command_line(cmdline)
        score += cmdline_score
        findings.extend(cmdline_findings)

        # 4. 检查进程行为
        behavior_score, behavior_findings = self._check_process_behavior(pid)
        score += behavior_score
        findings.extend(behavior_findings)

        # 5. 检查进程内存
        memory_score, memory_findings = self._check_process_memory(pid)
        score += memory_score
        findings.extend(memory_findings)

        # 6. 检查网络连接
        network_score, network_findings = self._check_network_connections(pid)
        score += network_score
        findings.extend(network_findings)

        return score > 30, findings  # 分数阈值设为30

    def _check_process_name(self, process_name):
        """检查进程名称"""
        score = 0
        findings = []

        process_name_lower = process_name.lower()

        # 检查是否在白名单中
        if process_name_lower in [p.lower() for p in self.system_process_whitelist]:
            return score, findings

        # 检查可疑进程名模式
        for pattern in self.suspicious_process_names:
            if re.search(pattern, process_name):
                score += 10
                findings.append(f"可疑进程名: {process_name} 匹配模式: {pattern}")
                break

        # 检查挖矿进程
        for pattern in self.mining_process_patterns:
            if re.search(pattern, process_name):
                score += 30
                findings.append(f"可能为挖矿进程: {process_name}")
                break

        return score, findings

    def _check_process_path(self, exe_path):
        """检查进程路径"""
        score = 0
        findings = []

        if not exe_path:
            return score, findings

        exe_path_lower = exe_path.lower()

        # 检查是否在可疑路径
        for pattern in self.suspicious_process_paths:
            if re.search(pattern, exe_path_lower):
                score += 20
                findings.append(f"进程位于可疑路径: {exe_path}")
                break

        # 检查路径是否为临时目录
        temp_dirs = [
            os.environ.get('TEMP', '').lower(),
            os.environ.get('TMP', '').lower(),
            r'c:\windows\temp',
            r'c:\users\*\appdata\local\temp',
        ]

        for temp_dir in temp_dirs:
            if temp_dir and temp_dir in exe_path_lower:
                score += 15
                findings.append(f"进程位于临时目录: {exe_path}")
                break

        return score, findings

    def _check_command_line(self, cmdline):
        """检查命令行参数"""
        score = 0
        findings = []

        if not cmdline:
            return score, findings

        cmdline_str = ' '.join(cmdline).lower()

        # 检查可疑命令行模式
        for pattern in self.suspicious_cmdline_patterns:
            if re.search(pattern, cmdline_str):
                score += 25
                findings.append(f"可疑命令行参数匹配: {pattern}")
                break

        # 检查常见恶意参数
        suspicious_flags = [
            '--mining', '--pool', '--wallet', '--stratum',
            '-o', '-u', '-p', '--url', '--user', '--pass',
            '--cuda', '--opencl', '--donate-level',
        ]

        for flag in suspicious_flags:
            if flag in cmdline_str:
                score += 10
                findings.append(f"可疑命令行标志: {flag}")
                break

        return score, findings

    def _check_process_behavior(self, pid):
        """检查进程行为"""
        score = 0
        findings = []

        try:
            proc = psutil.Process(pid)

            # 检查CPU使用率
            cpu_percent = proc.cpu_percent(interval=0.1)
            if cpu_percent > 80:  # 高CPU使用率
                score += 15
                findings.append(f"高CPU使用率: {cpu_percent}%")

            # 检查内存使用
            memory_info = proc.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)

            if memory_mb > 500:  # 内存使用超过500MB
                score += 10
                findings.append(f"高内存使用: {memory_mb:.2f} MB")

            # 检查线程数
            num_threads = proc.num_threads()
            if num_threads > 100:  # 线程数过多
                score += 10
                findings.append(f"线程数过多: {num_threads}")

            # 检查句柄数
            num_handles = proc.num_handles()
            if num_handles > 1000:  # 句柄数过多
                score += 10
                findings.append(f"句柄数过多: {num_handles}")

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            pass

        return score, findings

    def _check_process_memory(self, pid):
        """检查进程内存"""
        score = 0
        findings = []

        try:
            # 需要管理员权限
            if not self._is_admin():
                return score, findings

            proc = psutil.Process(pid)

            # 获取内存映射
            memory_maps = proc.memory_maps()

            # 检查是否有可执行内存区域
            executable_regions = 0
            for mmap in memory_maps:
                if 'x' in mmap.perms:  # 可执行权限
                    executable_regions += 1

            if executable_regions > 5:  # 可执行区域过多
                score += 20
                findings.append(f"发现 {executable_regions} 个可执行内存区域")

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            pass

        return score, findings

    def _check_network_connections(self, pid):
        """检查网络连接"""
        score = 0
        findings = []

        try:
            proc = psutil.Process(pid)

            # 获取网络连接
            connections = proc.connections()

            suspicious_ports = [3333, 4444, 5555, 6666, 7777, 8888, 9999, 8333, 9333]
            mining_pools = ['stratum', 'pool', 'mining', 'xmrpool', 'nanopool']

            for conn in connections:
                if hasattr(conn, 'raddr') and conn.raddr:
                    ip, port = conn.raddr

                    # 检查可疑端口
                    if port in suspicious_ports:
                        score += 20
                        findings.append(f"连接到可疑端口: {port}")

                    # 尝试解析域名
                    try:
                        import socket
                        hostname = socket.gethostbyaddr(ip)[0] if ip else ''

                        for pool in mining_pools:
                            if pool in hostname.lower():
                                score += 30
                                findings.append(f"连接到挖矿池: {hostname}")
                                break
                    except:
                        pass

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            pass

        return score, findings

    def _is_admin(self):
        """检查是否以管理员权限运行"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except:
            return False

    def kill_malicious_process(self, pid):
        """结束恶意进程"""
        try:
            proc = psutil.Process(pid)
            proc.terminate()

            # 等待进程结束
            try:
                proc.wait(timeout=5)
                return True, f"进程 {pid} 已结束"
            except psutil.TimeoutExpired:
                # 强制结束
                proc.kill()
                return True, f"进程 {pid} 已被强制结束"

        except psutil.NoSuchProcess:
            return True, f"进程 {pid} 不存在"
        except psutil.AccessDenied:
            return False, f"无权限结束进程 {pid}，请以管理员身份运行"
        except Exception as e:
            return False, f"结束进程 {pid} 失败: {str(e)}"


class HeuristicScanner:
    """启发式扫描器 - 用于检测类似恶意代码"""

    def __init__(self):
        # 恶意特征规则
        self.malicious_patterns = {
            'suspicious_strings': [
                r'(?i)(malware|trojan|virus|worm|ransomware|spyware|adware|rootkit|backdoor|botnet)',
                r'(?i)(keylogger|rat|remote.*access|exploit|payload)',
                r'(?i)(format.*c:|del.*/.*/.*/.*|rm.*-rf|shutdown.*/s|taskkill.*/f)',
                r'(?i)(reg.*add.*HKLM|reg.*add.*HKCU|reg.*add.*run)',
                r'(?i)(powershell.*-e|powershell.*-enc|certutil.*-decode)',
                r'http[s]?://(?!.*(microsoft|windowsupdate|adobe|apple|mozilla))[^\s]+',
                r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b:\d{1,5}',
                r'(?i)(\bmining\b|\bcryptominer\b|\bcrypto.*miner\b)',
            ],
            'suspicious_functions': [
                'CreateRemoteThread', 'WriteProcessMemory', 'VirtualAllocEx',
                'SetWindowsHookEx', 'keybd_event', 'mouse_event',
                'URLDownloadToFile', 'ShellExecute', 'WinExec',
                'RegSetValueEx', 'RegCreateKey', 'CreateService',
                'OpenProcessToken', 'AdjustTokenPrivileges',
            ],
            'suspicious_extensions': [
                '.bat', '.cmd', '.ps1', '.vbs', '.js', '.jar'  # 脚本类才可疑
            ],
            'sensitive_directories': [          # 真正的藏毒目录
                'AppData', 'Temp', 'Temporary',
                'Start Menu\\Programs\\Startup',
                'Microsoft\\Windows\\Start Menu\\Programs\\Startup'
            ]
        }

        # 文件签名检测
        self.file_signatures = {
            b'MZ': ('PE executable', '.exe'),
            b'\x7fELF': ('ELF executable', ''),
            b'#!': ('Script', ''),
            b'%PDF': ('PDF', '.pdf'),
            b'\x89PNG\r\n\x1a\n': ('PNG image', '.png'),
            b'\xff\xd8\xff': ('JPEG image', '.jpg'),
            b'GIF87a': ('GIF image', '.gif'),
            b'GIF89a': ('GIF image', '.gif'),
            b'BM': ('BMP image', '.bmp'),
            b'PK\x03\x04': ('ZIP archive', '.zip'),
            b'PK\x05\x06': ('ZIP archive', '.zip'),
            b'PK\x07\x08': ('ZIP archive', '.zip'),
            b'Rar!\x1a\x07\x00': ('RAR archive', '.rar'),
            b'\x1f\x8b\x08': ('GZIP archive', '.gz'),
            b'BZh': ('BZIP2 archive', '.bz2'),
            b'\xfd7zXZ\x00': ('XZ archive', '.xz'),
            b'<?xml': ('XML document', '.xml'),
            b'<html': ('HTML document', '.html'),
            b'\x00\x00\x01\xba': ('MPEG video', '.mpg'),
            b'\x00\x00\x01\xb3': ('MPEG video', '.mpg'),
            b'\x1a\x45\xdf\xa3': ('Matroska video', '.mkv'),
        }

        # 图片格式检测
        self.image_signatures = {
            b'\xff\xd8\xff': 'jpg',
            b'\x89PNG\r\n\x1a\n': 'png',
            b'GIF87a': 'gif',
            b'GIF89a': 'gif',
            b'BM': 'bmp',
            b'II*\x00': 'tiff',
            b'MM\x00*': 'tiff',
            b'\x00\x00\x01\x00': 'ico',
            b'\x00\x00\x02\x00': 'ico',
        }

    def analyze_file_content(self, filepath, max_size=10 * 1024 * 1024):
        """分析文件内容，检测可疑特征"""
        score = 0
        findings = []

        try:
            file_size = os.path.getsize(filepath)
            if file_size > max_size:
                return 0, ["文件过大，跳过内容分析"], 0

            with open(filepath, 'rb') as f:
                content = f.read()

            is_binary = self._is_binary(content)

            if is_binary:
                bin_score, bin_findings = self._analyze_binary(content, filepath)
                score += bin_score
                findings.extend(bin_findings)
            else:
                try:
                    text_content = content.decode('utf-8', errors='ignore')
                    text_score, text_findings = self._analyze_text(text_content, filepath)
                    score += text_score
                    findings.extend(text_findings)
                except:
                    pass

            entropy = self._calculate_entropy(content)
            if entropy > 7.5:
                score += 20
                findings.append(f"文件熵值过高 ({entropy:.2f})，可能被加密或混淆")

            file_type_findings = self._check_file_type(content, filepath)
            findings.extend(file_type_findings)

        except Exception as e:
            findings.append(f"分析文件时出错: {str(e)}")

        return score, findings, len(findings)

    def _is_binary(self, data):
        """判断是否为二进制文件"""
        text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
        if not data:
            return False

        non_text_count = 0
        for byte in data[:1024]:
            if byte not in text_chars:
                non_text_count += 1

        return non_text_count / min(len(data), 1024) > 0.3

    def _analyze_binary(self, content, filepath):
        """分析二进制文件"""
        score = 0
        findings = []

        try:
            if self._is_pe_file(content):
                pe_score, pe_findings = self._analyze_pe_file(content, filepath)
                score += pe_score
                findings.extend(pe_findings)

            malicious_patterns_score, malicious_findings = self._check_malicious_patterns(content)
            score += malicious_patterns_score
            findings.extend(malicious_findings)

            strings_score, strings_findings = self._extract_strings(content)
            score += strings_score
            findings.extend(strings_findings)

        except Exception as e:
            findings.append(f"二进制分析出错: {str(e)}")

        return score, findings

    def _analyze_text(self, text_content, filepath):
        """分析文本文件"""
        score = 0
        findings = []

        for pattern in self.malicious_patterns['suspicious_strings']:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            if matches:
                score += 10 * len(matches)
                for match in matches[:3]:
                    findings.append(f"发现可疑字符串: {match}")

        for func in self.malicious_patterns['suspicious_functions']:
            if func in text_content:
                score += 15
                findings.append(f"发现可疑函数调用: {func}")

        base64_pattern = r'[A-Za-z0-9+/]{20,}={0,2}'
        base64_matches = re.findall(base64_pattern, text_content)
        if base64_matches and len(base64_matches) > 5:
            score += 20
            findings.append(f"发现大量Base64编码 ({len(base64_matches)}处)")

        hex_pattern = r'[0-9A-Fa-f]{20,}'
        hex_matches = re.findall(hex_pattern, text_content)
        if hex_matches and len(hex_matches) > 3:
            score += 15
            findings.append(f"发现长十六进制字符串 ({len(hex_matches)}处)")

        return score, findings

    def _is_pe_file(self, content):
        """检查是否为PE文件"""
        return len(content) > 2 and content[:2] == b'MZ'

    def _analyze_pe_file(self, content, filepath):
        """分析PE文件"""
        score = 0
        findings = []

        try:
            pe = pefile.PE(data=content, fast_load=True)

            if hasattr(pe, 'OPTIONAL_HEADER'):
                entry_point = pe.OPTIONAL_HEADER.AddressOfEntryPoint
                if entry_point == 0:
                    score += 30
                    findings.append("入口点为0，可能为壳或混淆")

            if hasattr(pe, 'sections'):
                for section in pe.sections:
                    section_name = section.Name.decode('utf-8', errors='ignore').strip('\x00')

                    if section_name in ['.vmp', '.themida', '.aspack', '.upx']:
                        score += 40
                        findings.append(f"发现加壳节: {section_name}")

                    if section.Characteristics & 0xE0000020:
                        score += 25
                        findings.append(f"节可写可执行: {section_name}")

            if hasattr(pe, 'DIRECTORY_ENTRY_IMPORT'):
                for entry in pe.DIRECTORY_ENTRY_IMPORT:
                    dll_name = entry.dll.decode('utf-8', errors='ignore').lower()

                    suspicious_dlls = ['kernel32.dll', 'user32.dll', 'advapi32.dll',
                                       'ws2_32.dll', 'wininet.dll', 'urlmon.dll']
                    if dll_name in suspicious_dlls:
                        score += 5
                        findings.append(f"导入可疑DLL: {dll_name}")

            pe.close()

        except Exception as e:
            findings.append(f"PE文件分析出错: {str(e)}")

        return score, findings

    def _check_malicious_patterns(self, content):
        """检查恶意代码模式"""
        score = 0
        findings = []

        hex_content = content.hex()

        shellcode_patterns = [
            r'31c0', r'31db', r'31c9', r'31d2', r'cd80', r'b8',
        ]

        for pattern in shellcode_patterns:
            if pattern in hex_content:
                score += 20
                findings.append(f"发现可能的shellcode模式: {pattern}")
                break

        return score, findings

    def _extract_strings(self, content, min_length=4):
        """从二进制文件中提取可读字符串"""
        score = 0
        findings = []

        try:
            strings = []
            current_string = []

            for byte in content:
                if 32 <= byte <= 126:
                    current_string.append(chr(byte))
                else:
                    if len(current_string) >= min_length:
                        strings.append(''.join(current_string))
                    current_string = []

            if len(current_string) >= min_length:
                strings.append(''.join(current_string))

            for s in strings[:50]:
                s_lower = s.lower()

                if 'http://' in s_lower or 'https://' in s_lower:
                    if not any(domain in s_lower for domain in ['microsoft', 'windowsupdate', 'adobe']):
                        score += 15
                        findings.append(f"发现可疑URL: {s[:100]}")

                suspicious_commands = ['format', 'del ', 'rm ', 'shutdown', 'taskkill', 'reg add']
                for cmd in suspicious_commands:
                    if cmd in s_lower:
                        score += 10
                        findings.append(f"发现可疑命令: {s[:100]}")
                        break

                if 'system32' in s_lower or 'temp\\' in s_lower or 'startup' in s_lower:
                    score += 5
                    findings.append(f"发现可疑路径: {s[:100]}")

        except Exception as e:
            findings.append(f"字符串提取出错: {str(e)}")

        return score, findings

    def _calculate_entropy(self, data):
        """计算数据熵"""
        if not data:
            return 0

        entropy = 0
        counter = Counter(data)
        data_len = len(data)

        for count in counter.values():
            p_x = count / data_len
            entropy += -p_x * math.log2(p_x)

        return entropy

    def _detect_image_type(self, data):
        """检测图片类型"""
        for signature, img_type in self.image_signatures.items():
            if data.startswith(signature):
                return img_type
        return None

    def _check_file_type(self, content, filepath):
        """检查文件类型"""
        findings = []

        try:
            detected_type = self._detect_file_signature(content)
            ext = os.path.splitext(filepath)[1].lower()

            if detected_type:
                file_type, expected_ext = detected_type

                if ext and expected_ext and ext != expected_ext:
                    findings.append(f"文件扩展名({ext})与实际类型({file_type})不匹配")

                if file_type == 'PE executable' and ext not in ['.exe', '.dll', '.sys', '.scr']:
                    findings.append(f"可执行文件使用了非标准扩展名: {ext}")
            else:
                if ext in ['.exe', '.dll', '.sys']:
                    if not self._is_pe_file(content):
                        findings.append(f"文件扩展名({ext})但实际不是可执行文件")

            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.ico']:
                detected_img_type = self._detect_image_type(content[:32])
                if detected_img_type:
                    ext_without_dot = ext.lstrip('.')
                    if ext_without_dot not in detected_img_type and detected_img_type not in ext_without_dot:
                        findings.append(f"图片文件可能被伪装: 扩展名{ext}, 检测类型{detected_img_type}")
                else:
                    findings.append(f"文件有图片扩展名{ext}但实际不是图片")

        except Exception as e:
            findings.append(f"文件类型检测出错: {str(e)}")

        return findings

    def _detect_file_signature(self, data):
        """检测文件签名"""
        if len(data) < 4:
            return None

        for signature, (file_type, expected_ext) in self.file_signatures.items():
            if data[:len(signature)] == signature:
                return (file_type, expected_ext)

        return None

    def check_file_behavior(self, filepath):
        """检查文件行为特征"""
        score = 0
        findings = []

        try:
            filename = os.path.basename(filepath).lower()

            suspicious_names = [
                'svchost', 'lsass', 'csrss', 'smss', 'winlogon',
                'update', 'installer', 'setup', 'patch', 'crack',
                'keygen', 'loader', 'injector', 'hook', 'bypass'
            ]

            for name in suspicious_names:
                if name in filename:
                    score += 10
                    findings.append(f"可疑文件名包含: {name}")
                    break

            filepath_lower = filepath.lower()
            for sensitive_dir in self.malicious_patterns['sensitive_directories']:
                if sensitive_dir.lower() in filepath_lower:
                    score += 15
                    findings.append(f"文件位于敏感目录: {sensitive_dir}")
                    break

            ext = os.path.splitext(filepath)[1].lower()
            if ext in self.malicious_patterns['suspicious_extensions']:
                score += 5
                findings.append(f"可疑文件扩展名: {ext}")

            if os.name == 'nt':
                import ctypes
                FILE_ATTRIBUTE_HIDDEN = 0x2
                FILE_ATTRIBUTE_SYSTEM = 0x4

                attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
                if attrs != -1 and (attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM)):
                    score += 20
                    findings.append("文件具有隐藏或系统属性")

            try:
                file_size = os.path.getsize(filepath)
                if ext in ['.exe', '.dll']:
                    if file_size < 1024:
                        score += 30
                        findings.append("可执行文件过小，可能为下载器")
                    elif file_size > 50 * 1024 * 1024:
                        score += 20
                        findings.append("可执行文件过大，可能捆绑其他文件")
            except:
                pass

        except Exception as e:
            findings.append(f"行为分析出错: {str(e)}")

        return score, findings


class SimpleAntivirus:
    def __init__(self, enable_heuristic=True):
        self.virus_db = {}
        self.heuristic_scanner = HeuristicScanner() if enable_heuristic else None
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
            "virus_db_path": "virus_hash_lib.json",
            "default_scan_path": "C:\\",
            "auto_delete": False,
            "auto_quarantine": False,
            "heuristic_enabled": True
        }

    def load_settings(self, settings_file="antivirus_settings.json"):
        """加载设置"""
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    saved_settings = json.load(f)
                self.settings.update(saved_settings)
                return True, "设置加载成功"
            except Exception as e:
                return False, f"加载设置失败: {e}"
        return False, "设置文件不存在"

    def save_settings(self, settings_file="antivirus_settings.json"):
        """保存设置"""
        try:
            with open(settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            return True, "设置保存成功"
        except Exception as e:
            return False, f"保存设置失败: {e}"

    def load_virus_db(self, db_file=None):
        """加载病毒数据库"""
        if db_file is None:
            db_file = self.settings.get("virus_db_path", "virus_hash_lib.json")

        if os.path.exists(db_file):
            with open(db_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if self.is_ui_mode:
                print(f"[+] 加载原始数据: {len(data)} 条记录")
            self.virus_db = {}

            md5_count = 0
            for file_path, hash_info in data.items():
                if isinstance(hash_info, dict) and 'hash' in hash_info:
                    hash_value = hash_info['hash']
                    algorithm = hash_info.get('algorithm', 'md5').lower()

                    if algorithm == 'md5':
                        self.virus_db[hash_value] = file_path
                        md5_count += 1

            if self.is_ui_mode:
                print(f"[+] 成功加载 {md5_count} 个MD5哈希特征")
            return True, f"成功加载 {md5_count} 个MD5哈希特征"
        else:
            error_msg = f"哈希库未找到: {db_file}"
            if self.is_ui_mode:
                print(f"[!] {error_msg}")
            return False, error_msg

    def calculate_hash(self, filepath, algorithm="md5"):
        """计算文件哈希"""
        if algorithm == "md5":
            hasher = hashlib.md5()
        elif algorithm == "sha1":
            hasher = hashlib.sha1()
        elif algorithm == "sha256":
            hasher = hashlib.sha256()
        else:
            hasher = hashlib.md5()

        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            return hasher.hexdigest().lower()
        except Exception as e:
            return None

    def scan_file(self, filepath, algorithm="md5"):
        """扫描单个文件"""
        file_hash = self.calculate_hash(filepath, algorithm)

        if file_hash and file_hash in self.virus_db:
            return "hash", file_hash, 100, ["已知病毒哈希匹配"], None

        if self.heuristic_scanner:
            behavior_score, behavior_findings = self.heuristic_scanner.check_file_behavior(filepath)
            content_score, content_findings, finding_count = self.heuristic_scanner.analyze_file_content(filepath)

            total_score = behavior_score + content_score
            all_findings = behavior_findings + content_findings

            if total_score >= self.heuristic_threshold:
                return "heuristic", None, total_score, all_findings, file_hash

        return None, None, 0, [], file_hash

    def scan_directory(self, path, progress_callback=None):
        """扫描目录"""
        infected_files = []
        suspicious_files = []

        if self.is_ui_mode:
            print(f"[*] 开始扫描: {path}")
        start_time = time.time()

        file_count = 0
        total_files = 0

        for root, dirs, files in os.walk(path):
            total_files += len(files)

        if self.is_ui_mode:
            print(f"[*] 总计 {total_files} 个文件需要扫描")

        for root, dirs, files in os.walk(path):
            for file in files:
                if self.scan_canceled:
                    break

                full_path = os.path.join(root, file)
                file_count += 1
                self.stats["scanned"] = file_count

                if progress_callback and file_count % 10 == 0:
                    progress = (file_count / total_files) * 100
                    progress_callback(progress, file_count, total_files)

                if file_count % 100 == 0 and self.is_ui_mode:
                    elapsed = time.time() - start_time
                    files_per_sec = file_count / elapsed if elapsed > 0 else 0
                    print(f"[*] 已扫描 {file_count}/{total_files} 个文件, "
                          f"病毒: {self.stats['infected']}, 可疑: {self.stats['suspicious']}, "
                          f"速度: {files_per_sec:.1f} 文件/秒")

                try:
                    scan_type, virus_hash, score, findings, file_hash = self.scan_file(full_path, "md5")

                    if scan_type == "hash":
                        self.stats["infected"] += 1
                        infected_files.append({
                            "path": full_path,
                            "type": "已知病毒",
                            "hash": virus_hash,
                            "score": score,
                            "findings": findings
                        })

                    elif scan_type == "heuristic":
                        self.stats["suspicious"] += 1
                        suspicious_files.append({
                            "path": full_path,
                            "type": "可疑文件",
                            "hash": file_hash,
                            "score": score,
                            "findings": findings
                        })

                        if self.is_ui_mode and findings:
                            print(f"[!] 可疑文件: {full_path}")
                            for finding in findings[:3]:
                                print(f"    - {finding}")

                except Exception as e:
                    if self.is_ui_mode:
                        print(f"[!] 扫描文件失败 {full_path}: {e}")

        self.infected_files = infected_files
        self.suspicious_files = suspicious_files

        return infected_files + suspicious_files

    def generate_report(self, scan_results, output_file):
        """生成扫描报告"""
        report = {
            "scan_time": datetime.now().strftime("%Y-%m-d %H:%M:%S"),
            "scanned_files": self.stats["scanned"],
            "infected_files": self.stats["infected"],
            "suspicious_files": self.stats["suspicious"],
            "results": {
                "infected": self.infected_files,
                "suspicious": self.suspicious_files
            }
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        if self.is_ui_mode:
            print(f"[+] 报告已保存: {output_file}")
        return output_file

    def on_notification_clicked(self, toast):
        """点击通知时的回调函数"""
        print(f"[*] 通知被点击，准备处理 {len(self.infected_files)} 个病毒文件")

        if not self.infected_files and not self.suspicious_files:
            print("[!] 没有发现威胁文件")
            return

        def show_dialog():
            total_threats = len(self.infected_files) + len(self.suspicious_files)
            response = eg.buttonbox(
                f"发现 {len(self.infected_files)} 个病毒文件\n"
                f"发现 {len(self.suspicious_files)} 个可疑文件\n"
                f"总计 {total_threats} 个威胁\n\n"
                f"请选择操作:",
                "Command Antivirus",
                choices=["删除病毒", "隔离可疑", "查看详情", "全部忽略", "取消"]
            )

            if response == "删除病毒":
                self.delete_viruses()
            elif response == "隔离可疑":
                self.quarantine_suspicious()
            elif response == "查看详情":
                self.show_threat_details()
            elif response == "全部忽略":
                print("[*] 用户选择忽略所有威胁")

        dialog_thread = threading.Thread(target=show_dialog)
        dialog_thread.daemon = True
        dialog_thread.start()

    def delete_viruses(self):
        """删除病毒文件"""
        deleted = 0
        failed = 0

        for file_info in self.infected_files:
            try:
                if os.path.exists(file_info["path"]):
                    os.remove(file_info["path"])
                    print(f"[+] 已删除病毒文件: {file_info['path']}")
                    deleted += 1
            except Exception as e:
                print(f"[!] 删除失败 {file_info['path']}: {e}")
                failed += 1

        eg.msgbox(f"删除完成！\n成功删除: {deleted} 个病毒文件\n删除失败: {failed} 个文件", "结果")

    def quarantine_suspicious(self):
        """隔离可疑文件"""
        quarantine_dir = "quarantine"
        os.makedirs(quarantine_dir, exist_ok=True)

        quarantined = 0
        failed = 0

        for file_info in self.suspicious_files:
            try:
                if os.path.exists(file_info["path"]):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = os.path.basename(file_info["path"])
                    quarantine_path = os.path.join(quarantine_dir, f"{timestamp}_{filename}")

                    os.rename(file_info["path"], quarantine_path)

                    info_file = quarantine_path + ".info.json"
                    with open(info_file, "w", encoding="utf-8") as f:
                        json.dump(file_info, f, indent=2, ensure_ascii=False)

                    print(f"[+] 已隔离可疑文件: {file_info['path']} -> {quarantine_path}")
                    quarantined += 1
            except Exception as e:
                print(f"[!] 隔离失败 {file_info['path']}: {e}")
                failed += 1

        eg.msgbox(f"隔离完成！\n成功隔离: {quarantined} 个可疑文件\n隔离失败: {failed} 个文件", "结果")

    def show_threat_details(self):
        """显示威胁详情"""
        all_threats = self.infected_files + self.suspicious_files
        if not all_threats:
            eg.msgbox("没有发现威胁文件", "详情")
            return

        details = f"总计发现 {len(all_threats)} 个威胁文件:\n"
        details += f"- 已知病毒: {len(self.infected_files)} 个\n"
        details += f"- 可疑文件: {len(self.suspicious_files)} 个\n\n"

        for i, threat in enumerate(all_threats[:10], 1):
            file_name = os.path.basename(threat["path"])
            details += f"{i}. {file_name}\n"
            details += f"   类型: {threat['type']}\n"
            details += f"   路径: {threat['path']}\n"
            details += f"   评分: {threat['score']}\n"

            if threat.get("findings"):
                details += f"   发现: {threat['findings'][0]}\n"
                if len(threat["findings"]) > 1:
                    details += f"      还有 {len(threat['findings']) - 1} 个发现...\n"

            details += "\n"

        if len(all_threats) > 10:
            details += f"... 还有 {len(all_threats) - 10} 个文件未显示\n"

        eg.codebox("威胁文件详情", "详情", details)

    def scan_processes(self):
        """扫描运行中的进程"""
        print("[*] 开始扫描运行中的进程...")

        if not self._check_psutil():
            return [], "请先安装psutil库: pip install psutil"

        suspicious_processes = self.process_scanner.scan_running_processes()
        self.suspicious_processes = suspicious_processes
        self.stats["suspicious_processes"] = len(suspicious_processes)

        result_msg = f"发现 {len(suspicious_processes)} 个可疑进程"

        for proc in suspicious_processes:
            print(f"[!] 可疑进程: PID={proc['pid']}, 名称={proc['name']}")
            for finding in proc['findings'][:3]:
                print(f"    - {finding}")

        return suspicious_processes, result_msg

    def _check_psutil(self):
        """检查psutil是否可用"""
        try:
            import psutil
            return True
        except ImportError:
            if self.is_ui_mode:
                eg.msgbox("请先安装psutil库: pip install psutil", "缺少依赖")
            else:
                print("[!] 请先安装psutil库: pip install psutil")
            return False

    def kill_all_suspicious_processes(self):
        """结束所有可疑进程"""
        if not self.suspicious_processes:
            return True, "没有可疑进程需要结束"

        success_count = 0
        fail_count = 0
        messages = []

        for proc in self.suspicious_processes:
            pid = proc['pid']
            name = proc['name']

            success, message = self.process_scanner.kill_malicious_process(pid)

            if success:
                success_count += 1
                messages.append(f"✓ 进程 {name} (PID: {pid}) 已结束")
            else:
                fail_count += 1
                messages.append(f"✗ 进程 {name} (PID: {pid}) 结束失败: {message}")

        result_msg = f"结束进程完成:\n成功: {success_count} 个\n失败: {fail_count} 个"

        if messages:
            result_msg += "\n\n详细信息:\n" + "\n".join(messages)

        return success_count > 0, result_msg





clicked = False
def perform_file_scan(av, scan_path, scan_mode):
    """执行文件扫描"""
    confirm_msg = f"确认开始扫描:\n扫描路径: {scan_path}\n扫描模式: {scan_mode}\n\n开始扫描？"
    if not eg.ynbox(confirm_msg, "确认"):
        return

    av.scan_running = True
    av.scan_canceled = False
    av.stats = {"scanned": 0, "infected": 0, "suspicious": 0, "suspicious_processes": 0}
    av.infected_files = []
    av.suspicious_files = []

    scan_results = []

    def run_scan():
        nonlocal scan_results
        try:
            scan_results = av.scan_directory(scan_path, progress_callback=None)
        except Exception as e:
            eg.msgbox(f"扫描过程中出错: {str(e)}", "错误")
        finally:
            av.scan_running = False

    scan_thread = threading.Thread(target=run_scan)
    scan_thread.daemon = True
    scan_thread.start()

    last_update_time = time.time()
    while av.scan_running:
        current_time = time.time()

        if current_time - last_update_time >= 10:
            progress_msg = (f"正在扫描: {scan_path}\n"
                            f"已扫描文件: {av.stats['scanned']} 个\n"
                            f"发现病毒: {av.stats['infected']} 个\n"
                            f"可疑文件: {av.stats['suspicious']} 个\n")

            toast = Toast()
            toast.text_fields = ["Command Antivirus",f"{progress_msg}\n点击此处取消扫描"]

            def stop_scan(arg1):
                global clicked
                av.scan_canceled = True
                eg.msgbox("扫描已取消", "提示")
                clicked = True
                av.scan_running = False
                av.scan_canceled = True
            toast.on_activated = stop_scan
            toaster.show_toast(toast)
            last_update_time = current_time

        time.sleep(0.1)

    scan_thread.join(timeout=5)

    if av.scan_canceled:
        return

    report_dir = "scan_reports"
    os.makedirs(report_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(report_dir, f"scan_report_{timestamp}.json")
    av.generate_report(scan_results, report_file)

    result_msg = (f"扫描完成!\n\n"
                  f"扫描路径: {scan_path}\n"
                  f"扫描文件数: {av.stats['scanned']}\n"
                  f"发现病毒数: {av.stats['infected']}\n"
                  f"可疑文件数: {av.stats['suspicious']}\n"
                  f"总计威胁: {av.stats['infected'] + av.stats['suspicious']}")

    if av.stats['infected'] > 0 or av.stats['suspicious'] > 0:
        while True:
            choice = eg.buttonbox(f"{result_msg}\n\n请选择操作:", "扫描结果",
                                  choices=["处理威胁", "查看详情", "保存报告", "返回主菜单", "退出"])

            if choice == "处理威胁":
                av.on_notification_clicked(None)
            elif choice == "查看详情":
                av.show_threat_details()
            elif choice == "保存报告":
                save_path = eg.filesavebox("保存扫描报告", default="scan_report.json",
                                           filetypes=["*.json"])
                if save_path:
                    av.generate_report(av.infected_files + av.suspicious_files, save_path)
                    eg.msgbox(f"报告已保存到: {save_path}", "保存成功")
            elif choice == "返回主菜单":
                break
            elif choice == "退出" or choice is None:
                return
    else:
        eg.msgbox(f"{result_msg}\n\n恭喜! 未发现威胁文件。", "扫描结果")


def perform_process_scan(av):
    """执行进程扫描"""
    if not av._check_psutil():
        return

    if not eg.ynbox("开始扫描运行中的进程？\n\n注意：需要管理员权限才能扫描内存和结束进程。", "确认"):
        return

    # eg.msgbox("正在扫描运行中的进程，请稍候...", "扫描中")

    suspicious_processes, result_msg = av.scan_processes()

    if not suspicious_processes:
        eg.msgbox("未发现可疑进程。", "扫描结果")
        return

    details = f"发现 {len(suspicious_processes)} 个可疑进程:\n\n"

    for i, proc in enumerate(suspicious_processes[:10], 1):
        details += f"{i}. {proc['name']} (PID: {proc['pid']})\n"
        details += f"   路径: {proc['exe_path'] or '未知'}\n"

        if proc.get('findings'):
            details += f"   发现: {proc['findings'][0]}\n"

        details += "\n"

    if len(suspicious_processes) > 10:
        details += f"... 还有 {len(suspicious_processes) - 10} 个进程未显示\n"

    eg.codebox("可疑进程详情", "扫描结果", details)

    response = eg.buttonbox(f"{result_msg}\n\n请选择操作:", "进程扫描结果",
                            choices=["结束可疑进程", "查看进程详情", "保存报告", "返回"])

    if response == "结束可疑进程":
        success, message = av.kill_all_suspicious_processes()
        eg.msgbox(message, "结束进程结果")
    elif response == "保存报告":
        save_path = eg.filesavebox("保存进程扫描报告", default="process_scan.json",
                                   filetypes=["*.json"])
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump({
                    "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "suspicious_processes": suspicious_processes
                }, f, indent=2, ensure_ascii=False)
            eg.msgbox(f"报告已保存到: {save_path}", "保存成功")


def enhanced_silent_mode(args):
    """增强的静默后台扫描模式，带进度通知"""
    print("[*] 启动增强静默后台扫描...")

    # 创建杀毒软件实例
    av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)
    av.is_ui_mode = False

    # 加载病毒库
    success, message = av.load_virus_db()
    if not success:
        send_notification("加载病毒库失败", f"错误: {message}")
        return

    # 发送开始扫描通知
    send_notification("后台扫描开始",
                      f"路径: {args.path}\n时间: {datetime.now().strftime('%H:%M:%S')}")

    start_time = time.time()

    # # 定义进度回调函数
    # def progress_callback(progress, current, total):
    #     if int(progress) % 20 == 0:  # 每20%发送一次进度通知
    #         send_notification("扫描进度",
    #                           f"进度: {progress:.0f}%\n已扫描: {current}/{total} 文件")

    # 执行扫描
    try:
        results = av.scan_directory(args.path)
        elapsed = time.time() - start_time

        # 生成报告
        av.generate_report(results, args.output)

        # 发送扫描完成通知
        send_notification("扫描完成",
                          f"耗时: {elapsed:.1f}秒\n"
                          f"文件: {av.stats['scanned']}\n"
                          f"病毒: {av.stats['infected']}\n"
                          f"可疑: {av.stats['suspicious']}")

        # 如果有威胁，发送额外警告
        if av.stats['infected'] > 0:
            send_notification("⚠️ 发现病毒！",
                              f"发现 {av.stats['infected']} 个病毒文件\n"
                              f"建议立即处理！", warning=True)

    except Exception as e:
        send_notification("扫描错误", f"错误: {str(e)[:50]}...", error=True)

def show_scan_history():
    """显示扫描历史"""
    history_dir = "scan_reports"

    if not os.path.exists(history_dir):
        eg.msgbox("暂无扫描历史记录", "扫描历史")
        return

    report_files = [f for f in os.listdir(history_dir) if f.endswith('.json')]

    if not report_files:
        eg.msgbox("暂无扫描历史记录", "扫描历史")
        return

    report_files.sort(reverse=True)

    history_list = []
    for i, report_file in enumerate(report_files[:10], 1):
        file_path = os.path.join(history_dir, report_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                report = json.load(f)

            scan_time = report.get('scan_time', '未知时间')
            scanned_files = report.get('scanned_files', 0)
            infected_files = report.get('infected_files', 0)
            suspicious_files = report.get('suspicious_files', 0)

            history_list.append(f"{i}. {scan_time}")
            history_list.append(f"   扫描文件: {scanned_files} 个")
            history_list.append(f"   发现病毒: {infected_files} 个")
            history_list.append(f"   可疑文件: {suspicious_files} 个")
            history_list.append("")
        except:
            history_list.append(f"{i}. {report_file} (文件损坏)")
            history_list.append("")

    history_text = "\n".join(history_list)
    eg.codebox("扫描历史记录", "扫描历史", history_text)


def show_settings(av):
    """显示设置界面"""
    msg = "软件设置"
    title = "设置"
    field_names = ["病毒库路径", "默认扫描路径", "自动删除病毒", "自动隔离可疑文件", "启用启发式扫描"]

    current_settings = [
        av.settings.get("virus_db_path", "virus_hash_lib.json"),
        av.settings.get("default_scan_path", "C:\\"),
        "是" if av.settings.get("auto_delete", False) else "否",
        "是" if av.settings.get("auto_quarantine", False) else "否",
        "是" if av.settings.get("heuristic_enabled", True) else "否"
    ]

    while True:
        settings = eg.multenterbox(msg, title, field_names, current_settings)

        if settings is None:
            return

        error_msg = ""
        if not settings[0]:
            error_msg += "病毒库路径不能为空\n"
        if not settings[1]:
            error_msg += "默认扫描路径不能为空\n"

        if error_msg:
            eg.msgbox(error_msg, "设置错误")
            continue

        av.settings["virus_db_path"] = settings[0]
        av.settings["default_scan_path"] = settings[1]
        av.settings["auto_delete"] = (settings[2] == "是")
        av.settings["auto_quarantine"] = (settings[3] == "是")
        av.settings["heuristic_enabled"] = (settings[4] == "是")

        success, message = av.save_settings()
        if success:
            eg.msgbox("设置已保存", "成功")
            return
        else:
            eg.msgbox(f"保存设置失败: {message}", "错误")
            return


def send_notification(title, message, warning=False, error=False):
    """发送Toast通知的辅助函数"""
    toast = Toast()

    if warning:
        title = "⚠️ " + title
    elif error:
        title = "❌ " + title

    toast.text_fields = [title, message]

    toaster.show_toast(toast)

def show_about():
    """显示关于信息"""
    about_text = """Cmd Antivirus Release
版本: 3.3
作者: _Windows11
功能:
- 哈希匹配病毒检测
- 启发式扫描检测未知威胁
- 进程恶意代码扫描
- 文件内容分析
- 行为特征检测
- 隔离和删除威胁文件
- 详细的扫描报告

新增功能:
- 进程扫描：检测可疑运行进程
- 进程行为分析
- 网络连接检查
- 内存特征扫描

依赖库:
- psutil: 进程和系统信息
- pefile: PE文件分析
- easygui: 图形用户界面
- windows-toasts: Windows通知
- watchdog: 压缩文件分析

使用说明:
1. 选择扫描模式开始扫描
2. 查看扫描结果详情
3. 处理发现的威胁文件
4. 在设置中配置软件选项
©Copyright _Windows11 All Rights Reserved."""

    eg.msgbox(about_text, "关于")

def scan_process():
    ps = ProcessScanner()
    while True:
        ps.scan_running_processes()


def main():
    parser = argparse.ArgumentParser(description="Enhanced Command Antivirus")
    parser.add_argument("-p", "--path", default="C:\\", help="扫描路径")
    parser.add_argument("-o", "--output", default="scan_report.json", help="报告文件名")
    parser.add_argument("-ui", "--ui", action="store_true", help="使用GUI界面")
    parser.add_argument("--no-heuristic", action="store_true", help="禁用启发式扫描")
    parser.add_argument("--scan-processes", action="store_true", help="扫描运行中的进程")
    # 添加监控模式参数
    parser.add_argument("--monitor", metavar="PATH", help="监控指定目录，自动扫描新文件")
    parser.add_argument("--monitor-delay", type=int, default=2, help="监控模式下的扫描延迟（秒，默认2秒）")
    args = parser.parse_args()

    # 如果指定了监控模式
    if args.monitor:
        print(f"[*] 启动自动监控扫描模式")
        print(f"[*] 监控目录: {args.monitor}")

        av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)
        av.is_ui_mode = False

        # 加载病毒库
        success, message = av.load_virus_db()
        if not success:
            print(f"[!] 加载病毒库失败: {message}")
            print("[*] 监控模式将继续运行，但只能使用启发式扫描")

        # 启动监控模式
        start_monitor_mode(args.monitor, av)
        return

    if args.ui:
        ui_mode(args)
        return

    av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)
    av.load_virus_db()

    if args.scan_processes:
        print("[*] 开始进程扫描...")
        suspicious_processes, result_msg = av.scan_processes()
        print(f"\n[+] {result_msg}")

        if suspicious_processes:
            response = input("\n是否要结束这些可疑进程？(y/n): ")
            if response.lower() == 'y':
                success, message = av.kill_all_suspicious_processes()
                print(f"\n{message}")

        return

    print(f"[*] 开始扫描: {args.path}")
    print(f"[*] 启发式扫描: {'启用' if not args.no_heuristic else '禁用'}")
    start_time = time.time()

    results = av.scan_directory(args.path)

    elapsed = time.time() - start_time
    print(f"\n[+] 扫描完成!")
    print(f"    耗时: {elapsed:.2f}秒")
    print(f"    扫描文件: {av.stats['scanned']}")
    print(f"    发现病毒: {av.stats['infected']}")
    print(f"    可疑文件: {av.stats['suspicious']}")

    toast = Toast()
    toast.text_fields = [
        "扫描完成",
        f"耗时: {elapsed:.2f}s\n文件: {av.stats['scanned']}\n"
        f"病毒: {av.stats['infected']}\n可疑: {av.stats['suspicious']}\n"
        f"点击处理威胁"
    ]

    toast.on_activated = av.on_notification_clicked

    toaster.show_toast(toast)

    av.generate_report(results, args.output)

    print("\n[*] 程序运行中，可以点击通知处理威胁...")
    print("[*] 按 Ctrl+C 退出程序")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] 程序退出")

def ui_mode(args):
    global main_window
    """UI模式主函数"""
    main_window = 1
    av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)
    av.is_ui_mode = True
    av.load_settings()
    if started_ui_mode == 0:
        # 创建一个线程对象，target 指定要运行的函数
        scan_thread = threading.Thread(target=av.scan_processes)
        scan_thread.daemon = True  # 设置为“守护线程”，当主程序退出时，此线程也会被强制结束
        scan_thread.start()  # 启动线程，开始执行 run_scan 函数

        # 后台托盘运行模式
        av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)
        av.is_ui_mode = False
        av.load_settings()
        av.load_virus_db()

        # 创建并启动托盘管理器
        tray_manager = SystemTrayManager(av)

        # 显示提示信息
        eg.msgbox(
            "杀毒软件已在后台运行\n\n"
            "您可以在系统托盘找到杀毒软件图标\n"
            "右键点击图标可以查看状态和设置\n"
            "左键双击可以显示主界面",
            "后台运行中"
        )

        def temp2():
            tray_manager.run_in_tray()
        tray = threading.Thread(target=temp2)
        tray.daemon = True
        tray.start()
        def temp_func1():
            av = SimpleAntivirus(enable_heuristic=not args.no_heuristic)

            # 加载病毒库
            success, message = av.load_virus_db()
            if not success:
                print(f"[!] 加载病毒库失败: {message}")
                print("[*] 监控模式将继续运行，但只能使用启发式扫描")

            # 启动监控模式
            start_monitor_mode("C:\\", av)
        scan_zip = threading.Thread(target=temp_func1)
        scan_zip.daemon = True
        scan_zip.start()
        loading_result, message = av.load_virus_db()
        if not loading_result:
            response = eg.ynbox(f"加载病毒库失败:\n{message}\n\n是否继续？", "警告")
            if not response:
                return

    title = "Cmd Antivirus v3.3"
    msg = "请选择操作:"
    choices = ["快速扫描", "全盘扫描", "自定义扫描", "查看扫描历史", "备份MBR/EFI", "修复MBR/EFI", "设置", "关于"]# , "进程扫描", "退出" is wasted

    choice = eg.buttonbox(msg, title, choices=choices)

    # if choice is None or choice == "退出":
    #     break
    if choice == None:
        main_window = 0
    elif choice == "快速扫描":
        scan_path = "C:\\Windows\\System32"
        scan_mode = "快速扫描"
        perform_file_scan(av, scan_path, scan_mode)
    elif choice == "全盘扫描":
        scan_path = "C:\\"
        scan_mode = "全盘扫描"
        perform_file_scan(av, scan_path, scan_mode)
    elif choice == "自定义扫描":
        scan_path = eg.diropenbox("请选择要扫描的文件夹", "自定义扫描")
        if not scan_path:
            pass
        scan_mode = "自定义扫描"
        perform_file_scan(av, scan_path, scan_mode)
    elif choice == "进程扫描":
        perform_process_scan(av)
    elif choice == "查看扫描历史":
        show_scan_history()
    elif choice == "设置":
        show_settings(av)
    elif choice == "关于":
        show_about()
    elif choice == "备份MBR/EFI":
        os.system("fix_efi_mbr_aft10.exe --backup")
    elif choice == "备份MBR/EFI":
        os.system("fix_efi_mbr_aft10.exe --repair")

if __name__ == "__main__":
    try:
        import pefile
    except ImportError as e:
        print(f"[!] 缺少依赖库: {e}")
        print("[*] 请安装依赖: pip install pefile")
        sys.exit(1)

    try:
        import psutil
    except ImportError:
        print("[!] 缺少psutil库，进程扫描功能将不可用")
        print("[*] 如需使用进程扫描，请安装: pip install psutil")


    def main_loop():
        while True:
            time.sleep(0.06)
            continue

    loop = threading.Thread(target=main_loop)
    loop.daemon = False
    loop.start()

    main()

