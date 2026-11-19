cmake_minimum_required(VERSION 3.21)   # MSVC toolchain needs ≥3.20
project(PythonProject LANGUAGES C)

# ── Compiler detection ──────────────────────────────────────────────
# Must be MSVC for kernel-mode driver
if(NOT MSVC)
    message(FATAL_ERROR "This project requires the MSVC compiler (cl.exe).")
endif()

# ── C standard ──────────────────────────────────────────────────────
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

# ── WDK paths ───────────────────────────────────────────────────────
set(WDK_ROOT     "C:/Program Files (x86)/Windows Kits/10")
set(WDK_VERSION  "10.0.26100.0")

set(WDK_INCLUDE_KM     "${WDK_ROOT}/Include/${WDK_VERSION}/km")
set(WDK_INCLUDE_SHARED "${WDK_ROOT}/Include/${WDK_VERSION}/shared")
set(WDK_INCLUDE_UM     "${WDK_ROOT}/Include/${WDK_VERSION}/um")
set(WDK_LIB_KM         "${WDK_ROOT}/Lib/${WDK_VERSION}/km/x64")

# Verify WDK exists
if(NOT EXISTS "${WDK_INCLUDE_KM}/ntddk.h")
    message(WARNING "WDK not found at ${WDK_ROOT}\\${WDK_VERSION}")
    message(WARNING "Install via: https://learn.microsoft.com/en-us/windows-hardware/drivers/download-the-wdk")
    message(WARNING "CMake configured but compilation will fail until WDK is installed.")
endif()

# ── Driver target ───────────────────────────────────────────────────
add_library(kernel MODULE kernel.c)

target_include_directories(kernel PRIVATE
    ${WDK_INCLUDE_KM}
    ${WDK_INCLUDE_SHARED}
    ${WDK_INCLUDE_UM}
)

target_link_directories(kernel PRIVATE ${WDK_LIB_KM})

target_link_libraries(kernel
    ntoskrnl.lib
    hal.lib
    BufferOverflowK.lib   # /GS support in kernel
)

# ── Compiler options (kernel-mode specific) ─────────────────────────
target_compile_options(kernel PRIVATE
    # From WDK defaults
    /kernel                # Enable kernel-mode compilation semantics
    /DRIVER                # Legacy; /kernel supersedes but keep for compat

    # Warnings
    /W4                    # Level 4 warnings
    /WX                    # Treat warnings as errors (production quality)
    /wd4100                # "unreferenced formal parameter" — we use UNREFERENCED_PARAMETER
    /wd4201                # nameless struct/union (common in WDK headers)

    # Optimisation (Debug)
    $<$<CONFIG:Debug>:/Od>
    $<$<CONFIG:Debug>:/Ob0>

    # Optimisation (Release)
    $<$<CONFIG:Release>:/O2>
    $<$<CONFIG:Release>:/Ob2>

    # Defines
    /DUNICODE
    /D_UNICODE
    /D_AMD64_               # Target architecture (required by ntdef.h / wdm.h)
    # /D_KERNEL_MODE omitted — WDK headers (ntddk.h) define it automatically
    $<$<CONFIG:Debug>:/DDBG>
    $<$<CONFIG:Release>:/DNDEBUG>

    # Encoding — kernel.c has UTF-8 comments, MSVC defaults to GBK (936)
    /utf-8

    # Code-gen
    /GS                   # Buffer security check (OK with BufferOverflowK.lib)
    /guard:cf             # Control Flow Guard
    /Qspectre              # Spectre mitigations (MSVC 2017 15.5+)
    /Zi                   # Debug info (Debug)
    $<$<CONFIG:Release>:/Zi>  # PDB for release too (offline debugging)
)

# ── Linker options (kernel-mode) ────────────────────────────────────
target_link_options(kernel PRIVATE
    /DRIVER
    /SUBSYSTEM:NATIVE
    /ENTRY:DriverEntry
    /MANIFEST:NO            # kernel drivers cannot have manifests

    # Required: no user-mode CRT
    /NODEFAULTLIB
    /NODEFAULTLIB:libcmt
    /NODEFAULTLIB:libvcruntime
    /NODEFAULTLIB:msvcrt
    /NODEFAULTLIB:oldnames

    # Kernel-safe CRT
    /INCLUDE:__security_init_cookie   # if /GS used

    # Debug info
    /DEBUG

    # Release optimisation
    $<$<CONFIG:Release>:/OPT:REF>
    $<$<CONFIG:Release>:/OPT:ICF>
)

# ── Output ──────────────────────────────────────────────────────────
set_target_properties(kernel PROPERTIES
    SUFFIX          ".sys"
    OUTPUT_NAME     "pyav_kernel"
    PREFIX          ""
    C_STANDARD      11

    # Put the .sys directly in the build root for easy test-signing
    LIBRARY_OUTPUT_DIRECTORY         "${CMAKE_BINARY_DIR}"
    LIBRARY_OUTPUT_DIRECTORY_DEBUG   "${CMAKE_BINARY_DIR}"
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}"
)

# ── Post-build: test-sign the driver (optional) ─────────────────────
# Uncomment the block below after generating a self-signed certificate:
#
# add_custom_command(TARGET kernel POST_BUILD
#     COMMAND signtool sign /v /fd SHA256
#             /s Root /n "YourCertName"
#             "$<TARGET_FILE:kernel>"
#     COMMENT "Test-signing pyav_kernel.sys"
# )
# ── Before: run as Admin:  makecert -r -pe -ss PrivateCertStore -n "CN=PYAV" pyav.cer
# ── Then uncomment and replace "YourCertName" with "PYAV"

message(STATUS "WDK   : ${WDK_ROOT}\\${WDK_VERSION}")
message(STATUS "Target: pyav_kernel.sys (kernel-mode driver, x64)")

# ── BSOD test driver ────────────────────────────────────────────────
add_library(bsod MODULE bsod.c)
target_include_directories(bsod PRIVATE ${WDK_INCLUDE_KM} ${WDK_INCLUDE_SHARED} ${WDK_INCLUDE_UM})
target_link_directories(bsod PRIVATE ${WDK_LIB_KM})
target_link_libraries(bsod ntoskrnl.lib)
target_compile_options(bsod PRIVATE /kernel /DRIVER /W4 /wd4100 /wd4201 /DUNICODE /D_AMD64_ /utf-8)
target_link_options(bsod PRIVATE /DRIVER /SUBSYSTEM:NATIVE /ENTRY:DriverEntry /NODEFAULTLIB /MANIFEST:NO)
set_target_properties(bsod PROPERTIES SUFFIX ".sys" OUTPUT_NAME "bsod" PREFIX "")
message(STATUS "Target: bsod.sys (manual BSOD driver, VM only)")
