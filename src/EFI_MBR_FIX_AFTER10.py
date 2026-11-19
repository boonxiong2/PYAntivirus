#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UEFI/GPT 引导修复与检测工具
适用于 Windows 10 和 Windows 11 的现代引导环境
"""
from Cmd_Antivirus import send_notification
import os
import sys
import ctypes
import struct
import hashlib
import json
import logging
import subprocess
import argparse
from datetime import datetime
from pathlib import Path, PureWindowsPath
import win32api
import win32file
import win32con
import winioctlcon
import pywintypes

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('uefi_repair.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def is_admin():
    """检查是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def get_system_info():
    """获取详细的系统信息"""
    info = {
        "os_name": os.name,
        "platform": sys.platform,
    }

    try:
        import platform
        info["system"] = platform.system()
        info["release"] = platform.release()
        info["version"] = platform.version()
        info["architecture"] = platform.architecture()[0]
        info["processor"] = platform.processor()

        # 检测是UEFI还是BIOS启动
        try:
            firmware_type = ctypes.c_uint32()
            ctypes.windll.kernel32.GetFirmwareType(ctypes.byref(firmware_type))
            firmware_types = {
                1: "BIOS",
                2: "UEFI",
                3: "Unknown"
            }
            info["firmware_type"] = firmware_types.get(firmware_type.value, "Unknown")
        except:
            info["firmware_type"] = "Unknown (检测失败)"

    except Exception as e:
        info["error"] = str(e)

    return info


class UEFIProtector:
    """UEFI/GPT 引导保护器 - 检测和修复现代Windows引导"""

    def __init__(self):
        # GPT 分区表签名
        self.GPT_SIGNATURE = b'EFI PART'
        self.GPT_HEADER_SIZE = 92
        self.GPT_ENTRY_SIZE = 128

        # EFI 系统分区 GUID (标准)
        self.EFI_SYSTEM_PARTITION_GUID = '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'

        # Windows 引导管理器文件路径 (相对ESP分区)
        self.BOOT_FILES = {
            'bootmgfw.efi': r'EFI\Microsoft\Boot\bootmgfw.efi',
            'bootx64.efi': r'EFI\Boot\bootx64.efi',
            'BCD': r'EFI\Microsoft\Boot\BCD',
        }

        # 已知健康的引导文件哈希值（示例，实际应从干净系统获取）
        self.KNOWN_GOOD_HASHES = {
            # Windows 10/11 bootmgfw.efi 哈希示例（需从实际系统获取）
            'bootmgfw.efi': [],
        }

        # 备份目录
        self.backup_dir = "uefi_backups"
        os.makedirs(self.backup_dir, exist_ok=True)

        # 系统信息
        self.system_info = get_system_info()
        logger.info(f"系统信息: {self.system_info}")

    def get_disk_layout(self):
        """获取磁盘布局信息"""
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 'Get-Disk | Select-Object Number, PartitionStyle, Size, IsBoot | ConvertTo-Json'],
                capture_output=True,
                text=True,
                shell=True
            )

            if result.returncode == 0:
                try:
                    disks = json.loads(result.stdout)
                    if isinstance(disks, dict):
                        disks = [disks]
                    return disks
                except json.JSONDecodeError:
                    # 尝试解析多行输出
                    lines = result.stdout.strip().split('\n')
                    disks = []
                    for line in lines:
                        if line.strip():
                            disks.append({"raw": line})
                    return disks
            return []
        except Exception as e:
            send_notification("Get disk layout",f"获取磁盘布局失败: {e}", error=True)
            return []

    def get_efi_partition_info(self):
        """获取EFI系统分区信息"""
        try:
            # 使用 diskpart 或 PowerShell 获取ESP分区信息
            script = '''
$eps = Get-Partition | Where-Object {$_.Type -eq "System"}
foreach ($ep in $eps) {
    $disk = Get-Disk -Number $ep.DiskNumber
    [PSCustomObject]@{
        DiskNumber = $ep.DiskNumber
        PartitionNumber = $ep.PartitionNumber
        DriveLetter = if ($ep.DriveLetter) { [string]$ep.DriveLetter } else { "N/A" }
        Size = $ep.Size
        Type = $ep.Type
        PartitionStyle = $disk.PartitionStyle
        GptType = if ($ep.GptType) { $ep.GptType } else { "N/A" }
    }
} | ConvertTo-Json
'''

            result = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True,
                text=True,
                shell=True
            )

            if result.returncode == 0 and result.stdout.strip():
                try:
                    partitions = json.loads(result.stdout)
                    if isinstance(partitions, dict):
                        return [partitions]
                    return partitions
                except json.JSONDecodeError:
                    send_notification("Err",f"无法解析ESP分区信息: {result.stdout}", error=True)

            return []
        except Exception as e:
            send_notification("Get EFI partition info",f"获取ESP分区信息失败: {e}", warning=True)
            return []

    def mount_efi_partition(self):
        """尝试挂载EFI系统分区（如果需要）"""
        try:
            # 检查是否已挂载
            script = '''
$efiPartition = Get-Partition | Where-Object {$_.Type -eq "System" -and $_.DriveLetter} | Select-Object -First 1
if ($efiPartition) {
    $driveLetter = $efiPartition.DriveLetter + ":"
    Write-Host $driveLetter
} else {
    Write-Host "NOT_MOUNTED"
}
'''

            result = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True,
                text=True,
                shell=True
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if output != "NOT_MOUNTED" and len(output) == 2:
                    send_notification("Progress",f"ESP分区已挂载为: {output}")
                    return output

            # 尝试挂载第一个ESP分区
            logger.info("尝试挂载ESP分区...")
            mount_script = '''
$efiPartition = Get-Partition | Where-Object {$_.Type -eq "System"} | Select-Object -First 1
if ($efiPartition) {
    $driveLetter = (Get-ChildItem function:[g-z]: -n | Where-Object { !(Test-Path $_) } | Select-Object -First 1)
    if ($driveLetter) {
        $efiPartition | Set-Partition -NewDriveLetter $driveLetter[0]
        Write-Host ($driveLetter + ":")
    } else {
        Write-Host "NO_FREE_LETTER"
    }
} else {
    Write-Host "NO_ESP_FOUND"
}
'''

            result = subprocess.run(
                ['powershell', '-Command', mount_script],
                capture_output=True,
                text=True,
                shell=True
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if output.startswith("NO") or output == "":
                    send_notification("EFI disk layout cannot be displayed","无法挂载ESP分区",warning=True)
                    return None
                else:
                    send_notification("Success",f"成功挂载ESP分区为: {output}")
                    return output

            return None
        except Exception as e:
            send_notification("Failed to display EFI disk layout",f"挂载ESP分区失败: {e}")
            return None

    def analyze_boot_files(self, efi_drive=None):
        """分析引导文件完整性"""
        analysis = {
            "timestamp": datetime.now().isoformat(),
            "files": {},
            "issues": [],
            "warnings": [],
            "status": "unknown"
        }

        if not efi_drive:
            efi_partitions = self.get_efi_partition_info()
            if not efi_partitions:
                analysis["issues"].append("未找到EFI系统分区")
                analysis["status"] = "corrupted"
                return analysis

            # 尝试挂载第一个ESP分区
            efi_drive = self.mount_efi_partition()
            if not efi_drive:
                analysis["issues"].append("无法挂载EFI系统分区")
                analysis["status"] = "corrupted"
                return analysis

        # 检查关键引导文件
        all_files_exist = True
        for file_name, rel_path in self.BOOT_FILES.items():
            file_path = os.path.join(efi_drive, rel_path)
            file_info = {
                "path": file_path,
                "exists": False,
                "size": 0,
                "hash": None,
                "issues": []
            }

            if os.path.exists(file_path):
                file_info["exists"] = True
                try:
                    file_size = os.path.getsize(file_path)
                    file_info["size"] = file_size

                    # 计算文件哈希
                    with open(file_path, 'rb') as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                        file_info["hash"] = file_hash

                    # 检查文件大小合理性
                    if file_name.endswith('.efi'):
                        if file_size < 1024 or file_size > 10 * 1024 * 1024:  # 1KB - 10MB
                            file_info["issues"].append(f"文件大小异常: {file_size} 字节")
                    elif file_name == 'BCD':
                        if file_size < 256 or file_size > 2 * 1024 * 1024:  # 256字节 - 2MB
                            file_info["issues"].append(f"BCD文件大小异常: {file_size} 字节")

                except Exception as e:
                    file_info["issues"].append(f"读取文件失败: {e}")
            else:
                file_info["issues"].append("文件不存在")
                all_files_exist = False
                if file_name in ['bootmgfw.efi', 'BCD']:
                    analysis["issues"].append(f"关键引导文件缺失: {file_name}")

            analysis["files"][file_name] = file_info

        # 确定整体状态
        if not all_files_exist:
            analysis["status"] = "corrupted"
        elif analysis["issues"]:
            analysis["status"] = "warning"
        else:
            analysis["status"] = "healthy"

        return analysis

    def backup_boot_files(self, efi_drive=None):
        """备份引导文件"""
        logger.info("开始备份引导文件...")

        if not efi_drive:
            efi_drive = self.mount_efi_partition()
            if not efi_drive:
                logger.error("无法挂载EFI分区进行备份")
                return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_info = {
            "timestamp": timestamp,
            "system_info": self.system_info,
            "files": {}
        }

        # 创建备份目录
        backup_path = os.path.join(self.backup_dir, f"boot_backup_{timestamp}")
        os.makedirs(backup_path, exist_ok=True)

        # 备份每个文件
        for file_name, rel_path in self.BOOT_FILES.items():
            src_path = os.path.join(efi_drive, rel_path)
            dst_path = os.path.join(backup_path, file_name)

            file_info = {"backed_up": False}

            if os.path.exists(src_path):
                try:
                    import shutil
                    shutil.copy2(src_path, dst_path)

                    # 计算哈希
                    with open(dst_path, 'rb') as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()

                    file_info.update({
                        "backed_up": True,
                        "size": os.path.getsize(dst_path),
                        "hash": file_hash,
                        "source": src_path
                    })

                    logger.info(f"已备份: {file_name}")

                except Exception as e:
                    file_info["error"] = str(e)
                    logger.error(f"备份 {file_name} 失败: {e}")
            else:
                file_info["error"] = "源文件不存在"
                logger.warning(f"文件不存在: {src_path}")

            backup_info["files"][file_name] = file_info

        # 保存备份信息
        info_file = os.path.join(backup_path, "backup_info.json")
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(backup_info, f, indent=2, ensure_ascii=False)

        logger.info(f"引导文件备份完成: {backup_path}")
        return backup_path

    def repair_with_bootrec(self):
        """使用bootrec修复引导（UEFI模式）"""
        logger.info("使用bootrec修复UEFI引导...")

        if not is_admin():
            logger.error("需要管理员权限运行bootrec")
            return False

        commands = [
            ["bootrec", "/fixboot"],
            ["bootrec", "/rebuildbcd"],
            ["bcdboot", r"C:\Windows", "/s", "S:", "/f", "UEFI"],  # 假设S:是ESP分区
        ]

        results = []
        for cmd in commands:
            logger.info(f"执行命令: {' '.join(cmd)}")
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    shell=True
                )

                cmd_result = {
                    "command": ' '.join(cmd),
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "success": result.returncode == 0
                }

                results.append(cmd_result)

                if result.returncode == 0:
                    logger.info(f"命令成功: {result.stdout[:100]}...")
                else:
                    logger.error(f"命令失败: {result.stderr[:100]}...")

            except Exception as e:
                logger.error(f"执行命令异常: {e}")
                results.append({
                    "command": ' '.join(cmd),
                    "error": str(e),
                    "success": False
                })

        # 总结结果
        success_count = sum(1 for r in results if r.get("success", False))
        if success_count > 0:
            logger.info(f"修复完成，{success_count}/{len(commands)} 个命令成功")
            return True
        else:
            logger.error("所有修复命令都失败了")
            return False

    def repair_with_bcdboot(self):
        """使用bcdboot重新创建引导文件"""
        logger.info("使用bcdboot重新创建引导文件...")

        if not is_admin():
            logger.error("需要管理员权限运行bcdboot")
            return False

        # 首先找到ESP分区
        efi_drive = self.mount_efi_partition()
        if not efi_drive:
            logger.error("找不到ESP分区")
            return False

        # 获取Windows目录
        windows_dir = os.environ.get('SystemRoot', r'C:\Windows')

        # 构建bcdboot命令
        cmd = [
            "bcdboot",
            windows_dir,
            "/s", efi_drive.rstrip(':'),  # 去掉冒号
            "/f", "UEFI",
            "/v"  # 详细输出
        ]

        logger.info(f"执行命令: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                shell=True
            )

            if result.returncode == 0:
                logger.info("bcdboot执行成功")
                logger.info(f"输出: {result.stdout}")
                return True
            else:
                logger.error(f"bcdboot执行失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"执行bcdboot异常: {e}")
            return False

    def check_bcd_integrity(self):
        """检查BCD存储完整性"""
        logger.info("检查BCD存储完整性...")

        if not is_admin():
            logger.error("需要管理员权限检查BCD")
            return None

        try:
            # 使用bcdedit导出BCD信息
            result = subprocess.run(
                ["bcdedit", "/enum", "ALL"],
                capture_output=True,
                text=True,
                shell=True
            )

            analysis = {
                "has_windows_bootmgr": "Windows Boot Manager" in result.stdout,
                "has_windows_bootloader": "Windows Boot Loader" in result.stdout,
                "output_length": len(result.stdout),
                "raw_output": result.stdout[:1000] + "..." if len(result.stdout) > 1000 else result.stdout
            }

            if result.returncode == 0:
                if analysis["has_windows_bootmgr"] and analysis["has_windows_bootloader"]:
                    analysis["status"] = "healthy"
                    logger.info("BCD存储看起来正常")
                else:
                    analysis["status"] = "corrupted"
                    analysis["issues"] = ["BCD中缺少必要的引导项"]
                    logger.warning("BCD存储可能已损坏")
            else:
                analysis["status"] = "error"
                analysis["error"] = result.stderr
                logger.error(f"检查BCD失败: {result.stderr}")

            return analysis

        except Exception as e:
            logger.error(f"检查BCD完整性异常: {e}")
            return {"status": "error", "error": str(e)}

    def scan_full_system(self):
        """完整系统引导扫描"""
        logger.info("开始完整系统引导扫描...")

        results = {
            "timestamp": datetime.now().isoformat(),
            "system_info": self.system_info,
            "disks": self.get_disk_layout(),
            "efi_partitions": self.get_efi_partition_info(),
            "firmware_type": self.system_info.get("firmware_type", "Unknown")
        }

        # 分析引导文件
        efi_drive = self.mount_efi_partition()
        if efi_drive:
            results["boot_files_analysis"] = self.analyze_boot_files(efi_drive)
        else:
            results["boot_files_analysis"] = {"status": "error", "error": "无法挂载ESP分区"}

        # 检查BCD
        results["bcd_analysis"] = self.check_bcd_integrity()

        # 总体状态评估
        all_healthy = True
        issues = []

        if results["boot_files_analysis"].get("status") != "healthy":
            all_healthy = False
            issues.append("引导文件问题")

        if results["bcd_analysis"] and results["bcd_analysis"].get("status") != "healthy":
            all_healthy = False
            issues.append("BCD存储问题")

        if results["firmware_type"] != "UEFI":
            issues.append(f"非UEFI固件: {results['firmware_type']}")

        results["overall_status"] = "healthy" if all_healthy else "issues_found"
        results["issues"] = issues

        return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="UEFI/GPT引导修复工具 - 适用于Windows 10/11",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python uefi_gpt_repair.py --scan         # 扫描系统引导状态
  python uefi_gpt_repair.py --backup       # 备份引导文件
  python uefi_gpt_repair.py --repair       # 修复引导（使用bootrec）
  python uefi_gpt_repair.py --bcdboot      # 使用bcdboot重新创建引导
  python uefi_gpt_repair.py --check-bcd    # 检查BCD完整性

兼容性说明:
  • 本工具同时适用于 Windows 10 和 Windows 11
  • 需要UEFI固件和GPT磁盘分区
  • 需要以管理员身份运行
  • Win11的Secure Boot要求可能影响修复结果
        """
    )

    parser.add_argument("--scan", action="store_true", help="完整扫描系统引导状态")
    parser.add_argument("--backup", action="store_true", help="备份引导文件")
    parser.add_argument("--repair", action="store_true", help="使用bootrec修复引导")
    parser.add_argument("--bcdboot", action="store_true", help="使用bcdboot重新创建引导文件")
    parser.add_argument("--check-bcd", action="store_true", help="检查BCD存储完整性")
    parser.add_argument("--info", action="store_true", help="显示系统信息")

    args = parser.parse_args()

    # 检查管理员权限
    if not is_admin():
        logger.error("请以管理员身份运行此程序！")
        logger.error("右键点击程序，选择'以管理员身份运行'")
        return

    tool = UEFIProtector()

    if args.scan:
        print("\n" + "=" * 60)
        print("UEFI/GPT 引导系统扫描")
        print("=" * 60)

        results = tool.scan_full_system()

        print(f"\n固件类型: {results['firmware_type']}")
        print(f"系统架构: {tool.system_info.get('architecture', 'Unknown')}")

        print(f"\n磁盘布局:")
        for disk in results.get('disks', []):
            if isinstance(disk, dict):
                print(f"  磁盘#{disk.get('Number', '?')}: {disk.get('PartitionStyle', '?')}, "
                      f"引导盘: {disk.get('IsBoot', '?')}, 大小: {disk.get('Size', 0)}")

        print(f"\nEFI分区:")
        for part in results.get('efi_partitions', []):
            if isinstance(part, dict):
                print(f"  磁盘#{part.get('DiskNumber', '?')} 分区#{part.get('PartitionNumber', '?')}: "
                      f"盘符: {part.get('DriveLetter', 'N/A')}, 类型: {part.get('Type', '?')}")

        print(f"\n引导文件分析:")
        boot_analysis = results.get('boot_files_analysis', {})
        print(f"  状态: {boot_analysis.get('status', 'unknown')}")
        if boot_analysis.get('files'):
            for file_name, file_info in boot_analysis['files'].items():
                status = "✓" if file_info.get('exists') else "✗"
                print(f"  {status} {file_name}: {file_info.get('path', 'N/A')}")
                if file_info.get('issues'):
                    for issue in file_info['issues']:
                        print(f"    警告: {issue}")

        print(f"\nBCD存储分析:")
        bcd_analysis = results.get('bcd_analysis', {})
        print(f"  状态: {bcd_analysis.get('status', 'unknown')}")
        if bcd_analysis.get('issues'):
            for issue in bcd_analysis['issues']:
                print(f"    问题: {issue}")

        print(f"\n总体状态: {results.get('overall_status', 'unknown')}")
        if results.get('issues'):
            print(f"发现的问题: {', '.join(results['issues'])}")

        # 保存详细报告
        report_file = f"uefi_scan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n详细报告已保存到: {report_file}")

    elif args.backup:
        print("\n备份引导文件...")
        backup_path = tool.backup_boot_files()
        if backup_path:
            print(f"备份完成: {backup_path}")
        else:
            print("备份失败")

    elif args.repair:
        print("\n使用bootrec修复引导...")
        if tool.repair_with_bootrec():
            print("修复命令执行完成，建议重启系统")
        else:
            print("修复过程中出现问题")

    elif args.bcdboot:
        print("\n使用bcdboot重新创建引导文件...")
        if tool.repair_with_bcdboot():
            print("bcdboot执行成功，引导文件已重新创建")
        else:
            print("bcdboot执行失败")

    elif args.check_bcd:
        print("\n检查BCD存储完整性...")
        analysis = tool.check_bcd_integrity()
        if analysis:
            print(f"状态: {analysis.get('status', 'unknown')}")
            if analysis.get('has_windows_bootmgr'):
                print("✓ 找到 Windows Boot Manager")
            if analysis.get('has_windows_bootloader'):
                print("✓ 找到 Windows Boot Loader")
            if analysis.get('issues'):
                for issue in analysis['issues']:
                    print(f"! {issue}")

    elif args.info:
        print("\n系统信息:")
        for key, value in tool.system_info.items():
            print(f"  {key}: {value}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
