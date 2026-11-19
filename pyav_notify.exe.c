/*
 * PYAV Notification Helper
 * Tiny EXE — shows a MessageBox, exits.
 * Compiled without CRT: EntryPoint → MessageBoxW → ExitProcess
 */

#include <windows.h>

#pragma comment(linker, "/SUBSYSTEM:WINDOWS")
#pragma comment(linker, "/ENTRY:EntryPoint")
#pragma comment(linker, "/NODEFAULTLIB")
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "kernel32.lib")

void EntryPoint(void) {
    MessageBoxW(NULL,
        L"PYAV Kernel Driver v1.0.0\n"
        L"Process monitoring active.\n"
        L"Injection detection enabled.\n\n"
        L"Click OK to continue.",
        L"PYAV Security", MB_OK | MB_ICONINFORMATION | MB_TOPMOST);
    ExitProcess(0);
}
