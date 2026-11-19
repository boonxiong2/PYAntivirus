import win32serviceutil
import win32service
import win32event
import servicemanager
import socket
import sys
import os


class AntivirusService(win32serviceutil.ServiceFramework):
    _svc_name_ = "CommandAntivirusService"
    _svc_display_name_ = "命令行杀毒软件服务"
    _svc_description_ = "提供实时文件监控和病毒扫描服务"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)
        self.is_running = False

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_running = False

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()

    def main(self):
        from Cmd_Antivirus import SimpleAntivirus, start_monitor_mode

        self.is_running = True
        av = SimpleAntivirus(enable_heuristic=True)
        av.load_virus_db()

        # 监控关键目录
        monitor_paths = [
            os.path.join(os.path.expanduser("~"), "Downloads"),
            os.path.join(os.environ.get('APPDATA', ''), 'Local\\Temp')
        ]

        for path in monitor_paths:
            if os.path.exists(path):
                print(f"[服务] 开始监控: {path}")
                # 这里启动监控线程

        # 保持服务运行
        while self.is_running:
            import time
            time.sleep(1)