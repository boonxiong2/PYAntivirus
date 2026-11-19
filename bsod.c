/*
 * BSOD.sys — Manual crash for VM testing
 * Usage: sc create bsod type= kernel binPath= <path>\bsod.sys
 *        sc start bsod  ← 立即蓝屏
 */

#include <ntddk.h>

VOID Unload(PDRIVER_OBJECT DriverObject) {
    UNREFERENCED_PARAMETER(DriverObject);
}

NTSTATUS DriverEntry(PDRIVER_OBJECT DriverObject, PUNICODE_STRING RegistryPath) {
    UNREFERENCED_PARAMETER(RegistryPath);
    DriverObject->DriverUnload = Unload;
    DbgPrint("[BSOD] Triggering bugcheck in 3 seconds...\n");

    // Delayed work item so the driver loads first, then crashes
    // (otherwise sc start hangs)
    LARGE_INTEGER delay;
    delay.QuadPart = -3 * 10 * 1000 * 1000;  // 3 seconds
    KeDelayExecutionThread(KernelMode, FALSE, &delay);

    DbgPrint("[BSOD] NOW!\n");
    KeBugCheckEx(MANUALLY_INITIATED_CRASH,  // 0xE2
        0xDEAD,     // P1 — "BSOD"
        0xCAFE,     // P2 — "BY"
        0x2024,     // P3 — year
        0x1337);    // P4 — leet
    return STATUS_SUCCESS;
}
