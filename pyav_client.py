"""
PYAV — User-mode Python client for pyav_kernel.sys

Communicates with the kernel driver via IOCTLs through
CreateFileW + DeviceIoControl (ctypes).

Requires: Administrator privileges (driver must already be loaded).
          Run `sc create pyav type= kernel binPath= <path>\pyav_kernel.sys`
          then  `sc start pyav`
"""

import ctypes
from ctypes import wintypes

# ---------------------------------------------------------------------------
# Win32 API bindings
# ---------------------------------------------------------------------------
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
GENERIC_READ  = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80

CreateFileW = kernel32.CreateFileW
CreateFileW.restype  = wintypes.HANDLE
CreateFileW.argtypes = [
    wintypes.LPCWSTR,  # lpFileName
    wintypes.DWORD,    # dwDesiredAccess
    wintypes.DWORD,    # dwShareMode
    wintypes.LPVOID,   # lpSecurityAttributes
    wintypes.DWORD,    # dwCreationDisposition
    wintypes.DWORD,    # dwFlagsAndAttributes
    wintypes.HANDLE,   # hTemplateFile
]

DeviceIoControl = kernel32.DeviceIoControl
DeviceIoControl.restype  = wintypes.BOOL
DeviceIoControl.argtypes = [
    wintypes.HANDLE,    # hDevice
    wintypes.DWORD,     # dwIoControlCode
    wintypes.LPVOID,    # lpInBuffer
    wintypes.DWORD,     # nInBufferSize
    wintypes.LPVOID,    # lpOutBuffer
    wintypes.DWORD,     # nOutBufferSize
    ctypes.POINTER(wintypes.DWORD),  # lpBytesReturned
    wintypes.LPVOID,    # lpOverlapped
]

CloseHandle = kernel32.CloseHandle
CloseHandle.restype  = wintypes.BOOL
CloseHandle.argtypes = [wintypes.HANDLE]

# ---------------------------------------------------------------------------
# IOCTL codes  (CTL_CODE macro, METHOD_BUFFERED = 0, FILE_ANY_ACCESS = 0)
# ---------------------------------------------------------------------------
def _CTL_CODE(device_type, function):
    """CTL_CODE with METHOD_BUFFERED (0) and FILE_ANY_ACCESS (0)."""
    return (device_type << 16) | (function << 2)

IOCTL_PYAV_GET_VERSION     = _CTL_CODE(0x8030, 0x800)
IOCTL_PYAV_PROTECT_PROCESS = _CTL_CODE(0x8030, 0x801)
IOCTL_PYAV_UNPROTECT_PROC  = _CTL_CODE(0x8030, 0x802)
IOCTL_PYAV_QUERY_PROTECTED = _CTL_CODE(0x8030, 0x803)
IOCTL_PYAV_ENABLE_MONITOR  = _CTL_CODE(0x8030, 0x810)
IOCTL_PYAV_DISABLE_MONITOR = _CTL_CODE(0x8030, 0x811)
IOCTL_PYAV_KILL_PROCESS    = _CTL_CODE(0x8030, 0x820)
IOCTL_PYAV_GET_NOTIFY_FLAG = _CTL_CODE(0x8030, 0x821)
IOCTL_PYAV_SCAN_ALL_PROCESSES = _CTL_CODE(0x8030, 0x830)

# ---------------------------------------------------------------------------
# C structure mirrors  (x64 alignment, matches kernel.c)
# ---------------------------------------------------------------------------
class VersionInfo(ctypes.Structure):
    _fields_ = [
        ("major", wintypes.ULONG),
        ("minor", wintypes.ULONG),
        ("patch", wintypes.ULONG),
    ]

class ProtectRequest(ctypes.Structure):
    """Matches _PYAV_PROTECT_REQUEST in kernel.c (x64, 16 bytes)."""
    _fields_ = [
        ("process_id", wintypes.HANDLE),
        ("protect",    wintypes.BOOLEAN),
    ]

# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------
DEVICE_PATH = r"\\.\PyavKernel"


class PyavKernelError(Exception):
    """Raised when kernel communication fails."""
    pass


class PyavClient:
    """User-mode client for pyav_kernel.sys."""

    def __init__(self):
        self._handle: wintypes.HANDLE = INVALID_HANDLE_VALUE

    # ── context manager ─────────────────────────────────────────────
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    # ── open / close ────────────────────────────────────────────────
    def open(self) -> "PyavClient":
        if self._handle not in (None, INVALID_HANDLE_VALUE):
            raise PyavKernelError("Already connected.")

        h = CreateFileW(
            DEVICE_PATH,
            GENERIC_READ | GENERIC_WRITE,
            0, None, OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | 0x40000000,  # FILE_FLAG_OVERLAPPED for async IO
            None,
        )
        if h == INVALID_HANDLE_VALUE:
            raise PyavKernelError(
                f"Cannot open {DEVICE_PATH}. "
                f"Run as Administrator and ensure the driver is loaded. "
                f"(error {ctypes.get_last_error()})"
            )
        self._handle = h
        return self

    def close(self):
        if self._handle not in (None, INVALID_HANDLE_VALUE):
            CloseHandle(self._handle)
        self._handle = INVALID_HANDLE_VALUE

    # ── internal IOCTL helper ───────────────────────────────────────
    def _ioctl(self, code: int, in_buf=None, out_buf_size: int = 0) -> bytes:
        in_data = ctypes.cast(ctypes.pointer(in_buf), wintypes.LPVOID) if in_buf else None
        in_size = ctypes.sizeof(in_buf) if in_buf else 0
        out_buf  = ctypes.create_string_buffer(out_buf_size)
        returned = wintypes.DWORD(0)

        ok = DeviceIoControl(
            self._handle, code,
            in_data, in_size,
            out_buf, out_buf_size,
            ctypes.byref(returned),
            None,
        )
        if not ok:
            raise PyavKernelError(
                f"DeviceIoControl 0x{code:08X} failed (error {ctypes.get_last_error()})"
            )
        return out_buf.raw[:returned.value]

    # ── public API ──────────────────────────────────────────────────
    def get_version(self) -> VersionInfo:
        """Return driver version info."""
        raw = self._ioctl(IOCTL_PYAV_GET_VERSION, out_buf_size=ctypes.sizeof(VersionInfo))
        return VersionInfo.from_buffer_copy(raw)

    def protect_process(self, pid: int) -> None:
        """Add a process to the protected list (prevent termination)."""
        req = ProtectRequest(process_id=wintypes.HANDLE(pid), protect=True)
        self._ioctl(IOCTL_PYAV_PROTECT_PROCESS, req)

    def unprotect_process(self, pid: int) -> None:
        """Remove a process from the protected list."""
        req = ProtectRequest(process_id=wintypes.HANDLE(pid), protect=False)
        self._ioctl(IOCTL_PYAV_UNPROTECT_PROC, req)

    def list_protected(self) -> list[int]:
        """Return list of protected PIDs."""
        max_count = 256
        raw = self._ioctl(IOCTL_PYAV_QUERY_PROTECTED,
                          out_buf_size=max_count * ctypes.sizeof(wintypes.HANDLE))
        count = len(raw) // ctypes.sizeof(wintypes.HANDLE)
        pids = (wintypes.HANDLE * count).from_buffer_copy(raw)
        return [int(p) for p in pids]

    def enable_monitor(self) -> None:
        """Enable process creation/termination monitoring."""
        self._ioctl(IOCTL_PYAV_ENABLE_MONITOR)

    def disable_monitor(self) -> None:
        """Disable process creation/termination monitoring."""
        self._ioctl(IOCTL_PYAV_DISABLE_MONITOR)

    def kill_process(self, pid: int) -> None:
        """Terminate a process from kernel mode (safe: blocks system PIDs)."""
        raw = wintypes.HANDLE(pid)
        buf = (wintypes.HANDLE * 1)(raw)
        self._ioctl(IOCTL_PYAV_KILL_PROCESS, buf)

    def wait_ready_and_notify(self, exe_path: str) -> bool:
        """Poll GET_NOTIFY_FLAG (set when explorer.exe starts).
           Launch the notify EXE when flag is set."""
        import subprocess
        import time
        for _ in range(60):     # poll up to 60 seconds
            try:
                raw = self._ioctl(IOCTL_PYAV_GET_NOTIFY_FLAG, out_buf_size=1)
                if raw and raw[0]:
                    subprocess.Popen([exe_path])
                    return True
            except PyavKernelError:
                pass
            time.sleep(1)
        return False

    def scan_all_processes(self) -> list[tuple[int, str]]:
        """Ring0 进程扫描：返回内核视角全部 (pid, name) 列表。
           与用户态 psutil 列表对比可发现被摘链隐藏的进程。"""
        raw = self._ioctl(IOCTL_PYAV_SCAN_ALL_PROCESSES, out_buf_size=8192 * 24)
        procs = []
        for i in range(0, len(raw), 24):
            pid = int.from_bytes(raw[i:i + 8], "little")
            name = raw[i + 8:i + 24].split(b"\x00")[0].decode("ascii", errors="ignore")
            procs.append((pid, name))
        return procs


# ---------------------------------------------------------------------------
# Quick test  (python -m pyav_client)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys, ctypes, os

    # Parse --auto-launch <exe_path>
    auto_launch = None
    if "--auto-launch" in sys.argv:
        idx = sys.argv.index("--auto-launch")
        if idx + 1 < len(sys.argv):
            auto_launch = sys.argv[idx + 1]

    print("PYAV Kernel Client")
    print("=" * 40)

    try:
        with PyavClient() as pyav:
            ver = pyav.get_version()
            print(f"Driver version : v{ver.major}.{ver.minor}.{ver.patch}")
            print(f"Protected PIDs : {pyav.list_protected()}")
            print("Driver OK \u2713")

            # Determine notifier path
            _notify_exe = auto_launch
            if not _notify_exe:
                _notify_exe = os.path.join(os.path.dirname(__file__) or ".", "pyav_notify.exe")

            if os.path.exists(_notify_exe):
                print("[*] Waiting for user login (explorer.exe) ...")
                if pyav.wait_ready_and_notify(_notify_exe):
                    print("[✓] Notification sent")
                else:
                    print("[!] Timeout waiting for login")
            else:
                print(f"[!] {_notify_exe} not found, skipping notification")

            # Keep running (background monitor)
            print("[*] PYAV active. Press Ctrl+C to exit.")
            import time
            try:
                while True:
                    time.sleep(10)
            except KeyboardInterrupt:
                print("\n[*] Shutting down.")
    except PyavKernelError as e:
        print(f"Error: {e}", file=sys.stderr)
        ctypes.windll.user32.MessageBoxW(0,
            f"Failed to connect to driver.\n\n{e}",
            "PYAV Error", 0x10)
        sys.exit(1)
