#include <ntddk.h>

VOID DriverUnload(PDRIVER_OBJECT DriverObject) {
    UNREFERENCED_PARAMETER(DriverObject);
    DbgPrint("[PYAV] Kernel Driver Unloaded\n");
}

NTSTATUS DriverEntry(PDRIVER_OBJECT DriverObject, PUNICODE_STRING RegistryPath) {
    UNREFERENCED_PARAMETER(RegistryPath);
    DriverObject->DriverUnload = DriverUnload;
    DbgPrint("[PYAV] Kernel Driver Loaded! Process ID: %lu\n", PsGetCurrentProcessId());
    return STATUS_SUCCESS;
}