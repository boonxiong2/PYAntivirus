import argparse
import os
parser = argparse.ArgumentParser(description="Enhanced Command Antivirus")
parser.add_argument("-p", "--path", default="C:\\", help="扫描路径")
parser.add_argument("-o", "--output", default="scan_report.json", help="报告文件名")
parser.add_argument("-ui", "--ui", action="store_true", help="使用GUI界面")
parser.add_argument("--no-heuristic", action="store_true", help="禁用启发式扫描")
parser.add_argument("--scan-processes", action="store_true", help="扫描运行中的进程")
args = parser.parse_args()
command_ui = r'".\TI.exe" -U T -P E -Wait ".\Command antivirus.exe" -ui'
command_scan_pro = r'".\TI.exe" -U T -P E -Wait ".\Command antivirus.exe" --scan-processes'
if args.ui:
    os.system(f"{command_ui}")
if args.scan_processes:
    os.system(f"{command} --scan-processes")
