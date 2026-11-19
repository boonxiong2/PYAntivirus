import ctypes
from ctypes import wintypes
import struct
import os
import sys

# ── Windows API 声明 ──────────────────────────────────────────
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

# ── 常量定义（与驱动保持一致） ────────────────────────────────
PYAV_DEVICE_TYPE = 0x8030


# IOCTL 编码函数
def ctl_code(function, method=0, access=0):
    """CTL_CODE(DeviceType, Function, Method, Access)"""
    return (PYAV_DEVICE_TYPE << 16) | (access << 14) | (function << 2) | method


# IOCTL 码
IOCTL_PYAV_GET_VERSION = ctl_code(0x800)  # METHOD_BUFFERED
IOCTL_PYAV_PROTECT_PROCESS = ctl_code(0x801)
IOCTL_PYAV_UNPROTECT_PROC = ctl_code(0x802)
IOCTL_PYAV_QUERY_PROTECTED = ctl_code(0x803)
IOCTL_PYAV_ENABLE_MONITOR = ctl_code(0x810)
IOCTL_PYAV_DISABLE_MONITOR = ctl_code(0x811)
IOCTL_PYAV_KILL_PROCESS = ctl_code(0x820)
IOCTL_PYAV_GET_NOTIFY_FLAG = ctl_code(0x821)  # METHOD_BUFFERED
IOCTL_PYAV_SCAN_ALL_PROCESSES = ctl_code(0x830)


class IO:
    """PYAV 内核驱动通信客户端"""

    def __init__(self, device_path=r"\\.\PyavKernel"):
        self.device_path = device_path
        self.handle = None
        self._connected = False

    # ── 连接管理 ──────────────────────────────────────────────

    def connect(self):
        """打开驱动设备"""
        if self._connected:
            return True

        self.handle = kernel32.CreateFileW(
            self.device_path,
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        if self.handle == INVALID_HANDLE_VALUE:
            err = ctypes.get_last_error()
            raise RuntimeError(f"连接驱动失败 (错误码: {err})。"
                               f"请确认驱动已加载并以管理员身份运行。")

        self._connected = True
        return True

    def disconnect(self):
        """关闭驱动设备"""
        if self.handle and self.handle != INVALID_HANDLE_VALUE:
            kernel32.CloseHandle(self.handle)
            self.handle = None
            self._connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    # ── 底层 IOCTL 通信 ───────────────────────────────────────

    def _device_io_control(self, ioctl_code, in_data=None, out_size=0):
        """发送 IOCTL 请求"""
        if not self._connected:
            raise RuntimeError("未连接到驱动")

        # 准备输入缓冲区
        in_buf = ctypes.create_string_buffer(in_data) if in_data else None
        in_len = len(in_data) if in_data else 0

        # 准备输出缓冲区
        out_buf = ctypes.create_string_buffer(out_size) if out_size else None
        returned = wintypes.DWORD(0)

        # 调用 DeviceIoControl
        ret = kernel32.DeviceIoControl(
            self.handle,
            ioctl_code,
            in_buf, in_len,
            out_buf, out_size,
            ctypes.byref(returned),
            None,
        )

        if not ret:
            err = ctypes.get_last_error()
            raise RuntimeError(f"IOCTL 失败 (错误码: {err})")

        return out_buf.raw[:returned.value] if out_size else None

    # ── 功能 API ──────────────────────────────────────────────

    def get_version(self):
        """获取驱动版本"""
        out = self._device_io_control(IOCTL_PYAV_GET_VERSION, out_size=12)
        major, minor, patch = struct.unpack_from("<III", out)
        return major, minor, patch

    def protect_process(self, pid, protect=True):
        """保护/取消保护进程"""
        # PYAV_PROTECT_REQUEST: HANDLE (8字节) + BOOLEAN (1字节) + 补齐7字节 = 16字节
        # struct.pack("<Q?") 只有 9 字节，驱动检查 inLen<16 会拒绝，必须补齐
        in_data = struct.pack("<Q?", pid, protect) + b"\x00" * 7
        self._device_io_control(
            IOCTL_PYAV_PROTECT_PROCESS if protect else IOCTL_PYAV_UNPROTECT_PROC,
            in_data=in_data
        )

    def query_protected(self):
        """查询受保护进程列表"""
        # 最多 256 个 HANDLE，每个 8 字节
        out = self._device_io_control(IOCTL_PYAV_QUERY_PROTECTED, out_size=256 * 8)
        count = len(out) // 8
        pids = struct.unpack_from(f"<{count}Q", out)
        return list(pids)

    def enable_monitor(self):
        """启用进程监控"""
        self._device_io_control(IOCTL_PYAV_ENABLE_MONITOR)

    def disable_monitor(self):
        """禁用进程监控"""
        self._device_io_control(IOCTL_PYAV_DISABLE_MONITOR)

    def kill_process(self, pid):
        """终止进程（受安全限制保护）"""
        in_data = struct.pack("<Q", pid)
        self._device_io_control(IOCTL_PYAV_KILL_PROCESS, in_data=in_data)

    def get_notify_flag(self):
        """获取用户登录通知标志"""
        # 注意：此 IOCTL 使用 METHOD_NEITHER，需要特殊处理
        # 这里简化处理，使用 METHOD_BUFFERED 方式
        try:
            out = self._device_io_control(IOCTL_PYAV_GET_NOTIFY_FLAG, out_size=1)
            return bool(out[0])
        except:
            return False

    def scan_all_processes(self):
        """Ring0 进程扫描：返回内核视角的全部 (pid, 映像名) 列表"""
        # PYAV_PROCESS_ENTRY: HANDLE(8字节) + CHAR[16] = 24 字节，最多 8192 个
        out = self._device_io_control(IOCTL_PYAV_SCAN_ALL_PROCESSES, out_size=8192 * 24)
        procs = []
        for i in range(0, len(out), 24):
            pid, name = struct.unpack_from("<Q16s", out, i)
            procs.append((pid, name.split(b"\x00")[0].decode("ascii", errors="ignore")))
        return procs
