/*
 * PYAV - Kernel Driver Layer
 * Windows x64 kernel-mode driver (C11, MSVC + WDK 10)
 *
 * Responsibilities:
 *   - Process creation / termination monitoring (PsSetCreateProcessNotifyRoutineEx)
 *   - User-mode communication via IRP_MJ_DEVICE_CONTROL (IOCTLs)
 *   - Self-protection basics (ObRegisterCallbacks stub)
 */

#include <ntifs.h>
#include <wdm.h>
#include <ntstrsafe.h>
#include <ntimage.h>

/* PsGetProcessImageFileName - not in ntifs.h under /kernel */
NTKERNELAPI
CHAR*
PsGetProcessImageFileName(
    _In_ PEPROCESS Process
    );

/* PROCESS_TERMINATE 在 winnt.h（用户态），WDK 内核头没有，自己补 */
#ifndef PROCESS_TERMINATE
#define PROCESS_TERMINATE 0x0001
#endif
/* ObRegisterCallbacks 句柄剥离要用的进程权限位（同样来自 winnt.h） */
#ifndef PROCESS_CREATE_THREAD
#define PROCESS_CREATE_THREAD       0x0002
#define PROCESS_VM_OPERATION        0x0008
#define PROCESS_VM_WRITE            0x0020
#define PROCESS_CREATE_PROCESS      0x0080
#define PROCESS_SET_INFORMATION     0x0200
#define PROCESS_SUSPEND_RESUME      0x0800
#define PROCESS_QUERY_LIMITED_INFORMATION 0x1000
#endif

/* ------------------------------------------------------------------ */
/*  Constants                                                         */
/* ------------------------------------------------------------------ */

#define PYAV_DEVICE_NAME       L"\\Device\\PyavKernel"
#define PYAV_SYMLINK_NAME      L"\\DosDevices\\PyavKernel"
#define PYAV_DEVICE_TYPE        0x8030          /* custom device type  */
#define PYAV_TAG               'VAYP'           /* pool tag            */

/* IOCTL codes (CTL_CODE) - 0x800-0xFFF reserved for MethodNeither */
#define IOCTL_PYAV_GET_VERSION     CTL_CODE(PYAV_DEVICE_TYPE, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_PROTECT_PROCESS CTL_CODE(PYAV_DEVICE_TYPE, 0x801, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_UNPROTECT_PROC  CTL_CODE(PYAV_DEVICE_TYPE, 0x802, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_QUERY_PROTECTED CTL_CODE(PYAV_DEVICE_TYPE, 0x803, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_ENABLE_MONITOR  CTL_CODE(PYAV_DEVICE_TYPE, 0x810, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_DISABLE_MONITOR CTL_CODE(PYAV_DEVICE_TYPE, 0x811, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_KILL_PROCESS    CTL_CODE(PYAV_DEVICE_TYPE, 0x820, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_GET_NOTIFY_FLAG CTL_CODE(PYAV_DEVICE_TYPE, 0x821, METHOD_BUFFERED, FILE_ANY_ACCESS)
#define IOCTL_PYAV_SCAN_ALL_PROCESSES CTL_CODE(PYAV_DEVICE_TYPE, 0x830, METHOD_BUFFERED, FILE_ANY_ACCESS)

#define PYAV_VERSION_MAJOR  1
#define PYAV_VERSION_MINOR  0
#define PYAV_VERSION_PATCH  0

/* Max number of PIDs we track for process protection */
#define PYAV_MAX_PROTECTED  256

/* ------------------------------------------------------------------ */
/*  Structures                                                        */
/* ------------------------------------------------------------------ */

typedef struct _PYAV_VERSION_INFO {
    ULONG Major;
    ULONG Minor;
    ULONG Patch;
} PYAV_VERSION_INFO;

typedef struct _PYAV_PROTECT_REQUEST {
    HANDLE ProcessId;
    BOOLEAN Protect;           /* TRUE = protect, FALSE = unprotect */
} PYAV_PROTECT_REQUEST;

/* Ring0 进程扫描条目：PID + 映像名（PsGetProcessImageFileName 最多 15 字符） */
typedef struct _PYAV_PROCESS_ENTRY {
    HANDLE ProcessId;
    CHAR   ImageName[16];
} PYAV_PROCESS_ENTRY;

/* Protected process table - simple fixed-size array for demo.
 * In production you'd want an AVL / hash table with proper locking. */
typedef struct _PYAV_PROTECTED_TABLE {
    HANDLE Pids[PYAV_MAX_PROTECTED];
    ULONG  Count;
    FAST_MUTEX Lock;
} PYAV_PROTECTED_TABLE;

/* ------------------------------------------------------------------ */
/*  Globals                                                           */
/* ------------------------------------------------------------------ */

static PDEVICE_OBJECT  g_DeviceObject    = NULL;
static BOOLEAN         g_MonitorEnabled  = TRUE;   /* process monitor on by default */
static PYAV_PROTECTED_TABLE g_ProtectedTable = { 0 };

/* Callback handles */
static PVOID g_ProcessNotifyHandle = NULL;
static PVOID g_ThreadNotifyHandle   = NULL;
static PVOID g_ObCallbackHandle    = NULL;   /* reserved for ObRegisterCallbacks */
static LARGE_INTEGER g_CmCallbackHandle = {0};   /* registry callback cookie */

/* ------------------------------------------------------------------ */
/*  Protected-Table Helpers                                           */
/* ------------------------------------------------------------------ */

static BOOLEAN
PyavIsProcessProtected(_In_ HANDLE ProcessId)
{
    ULONG i;
    for (i = 0; i < g_ProtectedTable.Count; i++) {
        if (g_ProtectedTable.Pids[i] == ProcessId) {
            return TRUE;
        }
    }
    return FALSE;
}

static NTSTATUS
PyavAddProtectedProcess(_In_ HANDLE ProcessId)
{
    if (g_ProtectedTable.Count >= PYAV_MAX_PROTECTED) {
        return STATUS_INSUFFICIENT_RESOURCES;
    }
    g_ProtectedTable.Pids[g_ProtectedTable.Count++] = ProcessId;
    return STATUS_SUCCESS;
}

static NTSTATUS
PyavRemoveProtectedProcess(_In_ HANDLE ProcessId)
{
    ULONG i;
    for (i = 0; i < g_ProtectedTable.Count; i++) {
        if (g_ProtectedTable.Pids[i] == ProcessId) {
            /* Swap with last and shrink */
            g_ProtectedTable.Pids[i] = g_ProtectedTable.Pids[g_ProtectedTable.Count - 1];
            g_ProtectedTable.Count--;
            return STATUS_SUCCESS;
        }
    }
    return STATUS_NOT_FOUND;
}

/* ── Ready flag: set when explorer.exe starts (user logged in) ───── */
static BOOLEAN g_NotifyReady = FALSE;
static UNICODE_STRING g_ExplorerName = RTL_CONSTANT_STRING(L"explorer.exe");

/* ── Launch the notification EXE (via user-mode Python client) ──── */
NTSTATUS PyavLaunchNotify(VOID)
{
    if (g_NotifyReady) return STATUS_SUCCESS;
    g_NotifyReady = TRUE;
    DbgPrint("[PYAV] User logged in - notify EXE ready\n");
    return STATUS_SUCCESS;
}

NTSTATUS PyavLaunchNotify(VOID);  /* forward declaration */

/* ── Process Creation Callback (old style - no Ex, works on 24H2) ── */
static VOID
PyavProcessNotify(
    _In_ HANDLE  ParentId,
    _In_ HANDLE  ProcessId,
    _In_ BOOLEAN Create)
{
    UNREFERENCED_PARAMETER(ParentId);

    if (!g_MonitorEnabled) return;

    if (Create) {
        DbgPrint("[PYAV] Process created - PID: %lu\n",
                 HandleToULong(ProcessId));

        /* Get process image name from EPROCESS */
        PEPROCESS process;
        if (NT_SUCCESS(PsLookupProcessByProcessId(ProcessId, &process))) {
            CHAR* imageName = PsGetProcessImageFileName(process);
            if (imageName) {
                DbgPrint("[PYAV]   Image: %s\n", imageName);

                /* When explorer.exe starts → user logged in */
                ANSI_STRING ansiName;
                RtlInitAnsiString(&ansiName, imageName);
                UNICODE_STRING uniName;
                RtlAnsiStringToUnicodeString(&uniName, &ansiName, TRUE);
                if (RtlCompareUnicodeString(&uniName,
                    &g_ExplorerName, TRUE) == 0)
                {
                    PyavLaunchNotify();
                }
                RtlFreeUnicodeString(&uniName);
            }
            ObDereferenceObject(process);
        }
    } else {
        DbgPrint("[PYAV] Process terminated - PID: %lu\n",
                 HandleToULong(ProcessId));

        /* Clean up if it was in the protected table */
        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        PyavRemoveProtectedProcess(ProcessId);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);
    }
}

/* ── Safety: refuse to kill system-critical PIDs ──────────────────── */
static BOOLEAN
PyavIsCriticalProcess(_In_ HANDLE ProcessId)
{
    /* PID 4 = System, PID 8 = registry, PID ≤ 20 = critical system processes */
    ULONG pid = HandleToULong(ProcessId);
    if (pid <= 20) return TRUE;
    if (pid == 4 || pid == 8) return TRUE;
    return FALSE;
}

/* ── Terminate a process from kernel mode ────────────────────────── */
NTSTATUS
PyavTerminateProcess(_In_ HANDLE ProcessId)
{
    NTSTATUS status;
    PEPROCESS process = NULL;
    HANDLE hProcess = NULL;
    CLIENT_ID cid = { 0 };
    OBJECT_ATTRIBUTES oa = RTL_CONSTANT_OBJECT_ATTRIBUTES(NULL, 0);

    status = PsLookupProcessByProcessId(ProcessId, &process);
    if (!NT_SUCCESS(status)) {
        return status;
    }

    cid.UniqueProcess = ProcessId;
    status = ZwOpenProcess(&hProcess, PROCESS_TERMINATE, &oa, &cid);
    if (!NT_SUCCESS(status)) {
        ObDereferenceObject(process);
        return status;
    }

    status = ZwTerminateProcess(hProcess, 0);
    ZwClose(hProcess);
    ObDereferenceObject(process);
    return status;
}

/* ── ObRegisterCallbacks：受保护进程句柄剥离（防杀/防注入） ──────── */
#define PYAV_OB_ALTITUDE L"320001.1"

static OB_PREOP_CALLBACK_STATUS
PyavObPreOperationCallback(
    _In_ PVOID RegistrationContext,
    _Inout_ POB_PRE_OPERATION_INFORMATION OperationInformation)
{
    UNREFERENCED_PARAMETER(RegistrationContext);

    /* 只处理进程句柄创建（注册时已限定 OB_OPERATION_HANDLE_CREATE） */
    if (OperationInformation->ObjectType == *PsProcessType) {

        PEPROCESS process = (PEPROCESS)OperationInformation->Object;
        HANDLE pid = PsGetProcessId(process);

        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        BOOLEAN isProtected = PyavIsProcessProtected(pid);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);

        if (isProtected) {
            /* 剥离危险权限：杀进程/写内存/注入/改信息 */
            OperationInformation->Parameters->CreateHandleInformation.DesiredAccess &=
                ~(PROCESS_TERMINATE | PROCESS_VM_WRITE | PROCESS_VM_OPERATION |
                  PROCESS_CREATE_PROCESS | PROCESS_SET_INFORMATION |
                  PROCESS_SUSPEND_RESUME | PROCESS_CREATE_THREAD);
            /* 兜底保证可查询 */
            OperationInformation->Parameters->CreateHandleInformation.DesiredAccess |=
                PROCESS_QUERY_LIMITED_INFORMATION;
        }
    }
    return OB_PREOP_SUCCESS;
}

static NTSTATUS
PyavRegisterObCallbacks(VOID)
{
    OB_CALLBACK_REGISTRATION cbReg = { 0 };
    OB_OPERATION_REGISTRATION opRegs[1] = { 0 };
    UNICODE_STRING altitude = RTL_CONSTANT_STRING(PYAV_OB_ALTITUDE);

    cbReg.Version = OB_FLT_REGISTRATION_VERSION;
    cbReg.OperationRegistrationCount = 1;
    cbReg.Altitude = altitude;
    cbReg.RegistrationContext = NULL;
    cbReg.OperationRegistration = opRegs;

    opRegs[0].ObjectType = PsProcessType;  /* 成员是 POBJECT_TYPE*，正好存全局指针 */
    opRegs[0].Operations = OB_OPERATION_HANDLE_CREATE;
    opRegs[0].PreOperation = PyavObPreOperationCallback;
    opRegs[0].PostOperation = NULL;

    return ObRegisterCallbacks(&cbReg, &g_ObCallbackHandle);
}

/* ── Thread creation callback ────────────────────────────────────── */
static VOID
PyavThreadNotify(
    _In_ HANDLE  ProcessId,
    _In_ HANDLE  ThreadId,
    _In_ BOOLEAN Create)
{
    if (Create) {
        DbgPrint("[PYAV] Thread CREATE - PID: %lu  TID: %lu\n",
                 HandleToULong(ProcessId), HandleToULong(ThreadId));

        /* If this process is protected, flag it */
        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        BOOLEAN protected = PyavIsProcessProtected(ProcessId);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);
        if (protected) {
            DbgPrint("[PYAV] !!! Thread injected into PROTECTED PID: %lu\n",
                     HandleToULong(ProcessId));
        }
    }
}

/* ── Registry callback  (CmRegisterCallbackEx) ──────────────────── */
#define PYAV_REG_ALTITUDE L"320000.1"

static NTSTATUS
PyavRegistryCallback(
    _In_opt_ PVOID CallbackContext,
    _In_opt_ PVOID Argument1,
    _In_opt_ PVOID Argument2)
{
    UNREFERENCED_PARAMETER(CallbackContext);
    UNREFERENCED_PARAMETER(Argument2);

    REG_NOTIFY_CLASS op = (REG_NOTIFY_CLASS)(ULONG_PTR)Argument1;

    switch (op) {
    case RegNtPreDeleteKey:
        DbgPrint("[PYAV] Reg DELETE KEY\n");
        break;

    case RegNtPreDeleteValueKey: {
        PREG_DELETE_VALUE_KEY_INFORMATION info =
            (PREG_DELETE_VALUE_KEY_INFORMATION)Argument2;
        if (info && info->ValueName && info->ValueName->Buffer)
            DbgPrint("[PYAV] Reg DELETE VALUE - %wZ\n", info->ValueName);
        break;
    }

    default:
        break;
    }
    return STATUS_SUCCESS;
}

/* ------------------------------------------------------------------ */
/*  IRP Dispatch                                                      */
/* ------------------------------------------------------------------ */

static NTSTATUS
PyavDispatchCreateClose(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);
    Irp->IoStatus.Status      = STATUS_SUCCESS;
    Irp->IoStatus.Information = 0;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return STATUS_SUCCESS;
}

static NTSTATUS
PyavDispatchDeviceControl(_In_ PDEVICE_OBJECT DeviceObject, _In_ PIRP Irp)
{
    UNREFERENCED_PARAMETER(DeviceObject);

    PIO_STACK_LOCATION  stack   = IoGetCurrentIrpStackLocation(Irp);
    ULONG               code    = stack->Parameters.DeviceIoControl.IoControlCode;
    PVOID               inBuf   = Irp->AssociatedIrp.SystemBuffer;
    PVOID               outBuf  = Irp->AssociatedIrp.SystemBuffer;
    ULONG               inLen   = stack->Parameters.DeviceIoControl.InputBufferLength;
    ULONG               outLen  = stack->Parameters.DeviceIoControl.OutputBufferLength;
    NTSTATUS            status  = STATUS_SUCCESS;
    ULONG               info    = 0;

    switch (code) {

    case IOCTL_PYAV_GET_VERSION: {
        PYAV_VERSION_INFO ver = { PYAV_VERSION_MAJOR, PYAV_VERSION_MINOR, PYAV_VERSION_PATCH };
        if (outLen >= sizeof(ver)) {
            RtlCopyMemory(outBuf, &ver, sizeof(ver));
            info = sizeof(ver);
        } else {
            status = STATUS_BUFFER_TOO_SMALL;
        }
        break;
    }

    case IOCTL_PYAV_PROTECT_PROCESS: {
        PYAV_PROTECT_REQUEST req;
        if (inLen < sizeof(req)) { status = STATUS_BUFFER_TOO_SMALL; break; }
        RtlCopyMemory(&req, inBuf, sizeof(req));

        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        status = PyavAddProtectedProcess(req.ProcessId);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);

        if (NT_SUCCESS(status)) {
            DbgPrint("[PYAV] Protected PID: %lu\n", HandleToULong(req.ProcessId));
        }
        break;
    }

    case IOCTL_PYAV_UNPROTECT_PROC: {
        PYAV_PROTECT_REQUEST req;
        if (inLen < sizeof(req)) { status = STATUS_BUFFER_TOO_SMALL; break; }
        RtlCopyMemory(&req, inBuf, sizeof(req));

        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        status = PyavRemoveProtectedProcess(req.ProcessId);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);

        if (NT_SUCCESS(status)) {
            DbgPrint("[PYAV] Unprotected PID: %lu\n", HandleToULong(req.ProcessId));
        }
        break;
    }

    case IOCTL_PYAV_QUERY_PROTECTED: {
        /* Return count + up-to-N PIDs the caller can hold */
        ULONG maxPids = outLen / sizeof(HANDLE);
        ULONG count   = 0;
        PHANDLE pids  = (PHANDLE)outBuf;

        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        for (ULONG i = 0; i < g_ProtectedTable.Count && count < maxPids; i++) {
            pids[count++] = g_ProtectedTable.Pids[i];
        }
        info = count * sizeof(HANDLE);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);
        break;
    }

    case IOCTL_PYAV_ENABLE_MONITOR:
        g_MonitorEnabled = TRUE;
        DbgPrint("[PYAV] Process monitor ENABLED\n");
        break;

    case IOCTL_PYAV_DISABLE_MONITOR:
        g_MonitorEnabled = FALSE;
        DbgPrint("[PYAV] Process monitor DISABLED\n");
        break;

    case IOCTL_PYAV_GET_NOTIFY_FLAG: {
        /* Return 1 if explorer.exe has started (user logged in) */
        BOOLEAN ready = g_NotifyReady;
        RtlCopyMemory(outBuf, &ready, sizeof(ready));
        info = sizeof(ready);
        break;
    }

    case IOCTL_PYAV_SCAN_ALL_PROCESSES: {
        /* Ring0 进程扫描：PID 空间试探。
         * 被摘链（ActiveProcessLinks 断链）隐藏的进程仍在 PID 表里，
         * PsLookupProcessByProcessId 一样找得到——不需要硬编码 EPROCESS 偏移。 */
        ULONG maxEntries = outLen / sizeof(PYAV_PROCESS_ENTRY);
        ULONG count = 0;
        if (maxEntries == 0) { status = STATUS_BUFFER_TOO_SMALL; break; }
        if (maxEntries > 8192) maxEntries = 8192;

        for (ULONG pid = 4; pid < 0x40000; pid += 4) {
            PEPROCESS process = NULL;
            if (NT_SUCCESS(PsLookupProcessByProcessId((HANDLE)(ULONG_PTR)pid, &process))) {
                if (count < maxEntries) {
                    PYAV_PROCESS_ENTRY *entry = (PYAV_PROCESS_ENTRY *)outBuf + count;
                    entry->ProcessId = (HANDLE)(ULONG_PTR)pid;
                    CHAR *name = PsGetProcessImageFileName(process);
                    if (name != NULL) {
                        RtlCopyMemory(entry->ImageName, name, 15);
                        entry->ImageName[15] = 0;
                    } else {
                        entry->ImageName[0] = 0;
                    }
                }
                count++;
                ObDereferenceObject(process);
            }
        }
        info = min(count, maxEntries) * sizeof(PYAV_PROCESS_ENTRY);
        break;
    }

    case IOCTL_PYAV_KILL_PROCESS: {
        HANDLE targetPid;
        if (inLen < sizeof(targetPid)) { status = STATUS_BUFFER_TOO_SMALL; break; }
        RtlCopyMemory(&targetPid, inBuf, sizeof(targetPid));

        /* Safety: refuse to kill system critical processes */
        if (PyavIsCriticalProcess(targetPid)) {
            DbgPrint("[PYAV] BLOCKED kill of critical PID: %lu\n",
                     HandleToULong(targetPid));
            status = STATUS_ACCESS_DENIED;
            break;
        }

        /* Safety: refuse to kill a user-protected process */
        ExAcquireFastMutex(&g_ProtectedTable.Lock);
        BOOLEAN isProtected = PyavIsProcessProtected(targetPid);
        ExReleaseFastMutex(&g_ProtectedTable.Lock);
        if (isProtected) {
            status = STATUS_ACCESS_DENIED;
            break;
        }

        status = PyavTerminateProcess(targetPid);
        if (NT_SUCCESS(status)) {
            DbgPrint("[PYAV] Killed PID: %lu\n", HandleToULong(targetPid));
        } else {
            DbgPrint("[PYAV] Failed to kill PID %lu: 0x%08X\n",
                     HandleToULong(targetPid), status);
        }
        break;
    }

    default:
        status = STATUS_INVALID_DEVICE_REQUEST;
        break;
    }

    Irp->IoStatus.Status      = status;
    Irp->IoStatus.Information = info;
    IoCompleteRequest(Irp, IO_NO_INCREMENT);
    return status;
}

/* ------------------------------------------------------------------ */
/*  DriverEntry / Unload                                               */
/* ------------------------------------------------------------------ */

VOID
DriverUnload(_In_ PDRIVER_OBJECT DriverObject)
{
    UNREFERENCED_PARAMETER(DriverObject);
    NTSTATUS status;

    /* Unregister process notify */
    if (g_ProcessNotifyHandle != NULL) {
        status = PsSetCreateProcessNotifyRoutine(PyavProcessNotify, TRUE);
        if (!NT_SUCCESS(status)) {
            DbgPrint("[PYAV] WARN: process notify unregister failed: 0x%08X\n", status);
        }
        g_ProcessNotifyHandle = NULL;
        DbgPrint("[PYAV] Process notify routine unregistered\n");
    }

    /* Unregister thread notify */
    if (g_ThreadNotifyHandle != NULL) {
        status = PsRemoveCreateThreadNotifyRoutine(PyavThreadNotify);
        if (!NT_SUCCESS(status)) {
            DbgPrint("[PYAV] WARN: thread notify unregister failed: 0x%08X\n", status);
        }
        g_ThreadNotifyHandle = NULL;
        DbgPrint("[PYAV] Thread notify routine unregistered\n");
    }

    /* ObCallbacks cleanup (reserved) */
    if (g_ObCallbackHandle != NULL) {
        ObUnRegisterCallbacks(g_ObCallbackHandle);
        g_ObCallbackHandle = NULL;
    }

    /* Unregister registry callback */
    if (g_CmCallbackHandle.QuadPart != 0) {
        CmUnRegisterCallback(g_CmCallbackHandle);
        g_CmCallbackHandle.QuadPart = 0;
        DbgPrint("[PYAV] Registry callback unregistered\n");
    }

    /* Delete symlink + device */
    UNICODE_STRING symlink = RTL_CONSTANT_STRING(PYAV_SYMLINK_NAME);
    IoDeleteSymbolicLink(&symlink);

    if (g_DeviceObject != NULL) {
        IoDeleteDevice(g_DeviceObject);
    }

    DbgPrint("[PYAV] Kernel driver unloaded\n");
}

NTSTATUS
DriverEntry(_In_ PDRIVER_OBJECT DriverObject, _In_ PUNICODE_STRING RegistryPath)
{
    UNREFERENCED_PARAMETER(RegistryPath);

    NTSTATUS       status;
    UNICODE_STRING devName;
    UNICODE_STRING symlink;

    DbgPrint("[PYAV] ===========================================\n");
    DbgPrint("[PYAV] Kernel Driver v%d.%d.%d loading...\n",
             PYAV_VERSION_MAJOR, PYAV_VERSION_MINOR, PYAV_VERSION_PATCH);
    DbgPrint("[PYAV] ===========================================\n");

    /* ---- 1. Init dispatch table ---- */
    DriverObject->MajorFunction[IRP_MJ_CREATE]         = PyavDispatchCreateClose;
    DriverObject->MajorFunction[IRP_MJ_CLOSE]          = PyavDispatchCreateClose;
    DriverObject->MajorFunction[IRP_MJ_DEVICE_CONTROL] = PyavDispatchDeviceControl;
    DriverObject->DriverUnload                         = DriverUnload;

    /* ---- 2. Create device object ---- */
    RtlInitUnicodeString(&devName, PYAV_DEVICE_NAME);
    status = IoCreateDevice(
        DriverObject,
        0,                              /* DeviceExtensionSize */
        &devName,
        PYAV_DEVICE_TYPE,
        0,                              /* DeviceCharacteristics */
        FALSE,                          /* Exclusive */
        &g_DeviceObject);

    if (!NT_SUCCESS(status)) {
        DbgPrint("[PYAV] IoCreateDevice failed: 0x%08X\n", status);
        return status;
    }

    /* Use buffered I/O for simplicity */
    g_DeviceObject->Flags |= DO_BUFFERED_IO;

    /* ---- 3. Create symbolic link ---- */
    RtlInitUnicodeString(&symlink, PYAV_SYMLINK_NAME);
    status = IoCreateSymbolicLink(&symlink, &devName);
    if (!NT_SUCCESS(status)) {
        DbgPrint("[PYAV] IoCreateSymbolicLink failed: 0x%08X\n", status);
        IoDeleteDevice(g_DeviceObject);
        g_DeviceObject = NULL;
        return status;
    }

    /* ---- 4. Register process notification (old style - no Ex, works on 24H2) ---- */
    status = PsSetCreateProcessNotifyRoutine(PyavProcessNotify, FALSE);
    if (!NT_SUCCESS(status)) {
        DbgPrint("[PYAV] PsSetCreateProcessNotifyRoutine failed: 0x%08X\n", status);
        /* Non-fatal - driver still loads */
    } else {
        g_ProcessNotifyHandle = (PVOID)1;  /* marker */
        DbgPrint("[PYAV] Process notify routine registered\n");
    }

    /* ---- 5. Register thread notification ---- */
    status = PsSetCreateThreadNotifyRoutine(PyavThreadNotify);
    if (!NT_SUCCESS(status)) {
        DbgPrint("[PYAV] PsSetCreateThreadNotifyRoutine failed: 0x%08X\n", status);
    } else {
        g_ThreadNotifyHandle = (PVOID)1;
        DbgPrint("[PYAV] Thread notify routine registered\n");
    }

    /* ---- 5.5 Register registry notification ---- */
    {
        UNICODE_STRING altitude = RTL_CONSTANT_STRING(PYAV_REG_ALTITUDE);
        status = CmRegisterCallbackEx(
            PyavRegistryCallback,
            &altitude,
            DriverObject,
            NULL,           /* context */
            &g_CmCallbackHandle,
            NULL            /* reserved */
        );
        if (!NT_SUCCESS(status)) {
            DbgPrint("[PYAV] CmRegisterCallbackEx failed: 0x%08X\n", status);
        } else {
            DbgPrint("[PYAV] Registry callback registered\n");
        }
    }

    /* ---- 6. Init protected table ---- */
    ExInitializeFastMutex(&g_ProtectedTable.Lock);
    g_ProtectedTable.Count = 0;

    /* ---- 7. ObRegisterCallbacks：受保护进程句柄剥离 ---- */
    status = PyavRegisterObCallbacks();
    if (!NT_SUCCESS(status)) {
        DbgPrint("[PYAV] ObRegisterCallbacks failed: 0x%08X (non-fatal)\n", status);
    } else {
        DbgPrint("[PYAV] Ob callbacks registered (handle stripping)\n");
    }

    DbgPrint("[PYAV] Driver loaded successfully. Device: %wZ\n", &symlink);
    return STATUS_SUCCESS;
}
