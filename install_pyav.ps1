<#
.SYNOPSIS
    PYAV — All-in-One Installer
    Integrates kernel driver + notification EXE + Python client + auto-start.
.DESCRIPTION
    Run as Administrator in the project root or the deployment folder.
    Installs: pyav_kernel.sys → system service
              pyav_notify.exe      → background notification
              pyav_client.py       → IOCTL communication
              Scheduled task       → auto-start at user login
.PARAMETER BuildDir
    Path to build output containing .sys and .exe (optional, auto-detected).
#>
param(
    [string]$BuildDir = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSCommandPath -Parent

# ── File paths ──────────────────────────────────────────────────────
# Try to locate build artifacts
$Possible = @(
    $BuildDir,
    "$ProjectRoot\out\build\x64-Debug",
    "$ProjectRoot"
) | Where-Object { $_ -ne "" }

$SysPath  = $null
$ExePath  = $null
foreach ($d in $Possible) {
    $s = "$d\pyav_kernel.sys"
    $e = "$d\pyav_notify.exe"
    if ((Test-Path $s) -and (Test-Path $e)) {
        $SysPath = $s; $ExePath = $e; break
    }
}

if (-not $SysPath) {
    Write-Host "[FAIL] Cannot find pyav_kernel.sys and pyav_notify.exe" -Foreground Red
    Write-Host "       Build first: cmake --build out/build/x64-Debug"
    Write-Host "       Or pass: -BuildDir C:\Path\To\Build"
    exit 1
}

$ClientPath  = "$ProjectRoot\pyav_client.py"
if (-not (Test-Path $ClientPath)) {
    Write-Host "[FAIL] pyav_client.py not found at $ClientPath" -Foreground Red
    exit 1
}

# ── Admin check ─────────────────────────────────────────────────────
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "[FAIL] Run as Administrator!" -Foreground Red
    exit 1
}

Write-Host @"
╔═══════════════════════════════════════╗
║         PYAV Installer v1.0          ║
╚═══════════════════════════════════════╝
"@ -Foreground Cyan

# ── 1. Test-signing check ──────────────────────────────────────────
Write-Host "[1/5] Checking test-signing..." -Foreground Yellow
$ts = (bcdedit /enum 2>$null | Select-String "testsigning").ToString() -match "Yes"
if (-not $ts) {
    Write-Host "[!] Test signing OFF. Enable and reboot:" -Foreground Yellow
    Write-Host "    bcdedit /set testsigning on" -Foreground White
    Write-Host "    shutdown /r /t 0" -Foreground White
    $yn = Read-Host "    Reboot now? (y/N)"
    if ($yn -eq 'y') { shutdown /r /t 0; exit }
    Write-Host "[!] Continuing without test signing — driver may fail to load" -Foreground Yellow
} else {
    Write-Host "[✓] Test signing ON" -Foreground Green
}

# ── 2. Sign the driver ─────────────────────────────────────────────
Write-Host "[2/5] Test-signing driver..." -Foreground Yellow
$cert = New-SelfSignedCertificate -Subject "CN=PYAV" -Type CodeSigningCert `
    -CertStoreLocation "Cert:\CurrentUser\My" -KeyUsage DigitalSignature 2>$null
$certPath = Join-Path $env:TEMP "pyav_cert.cer"
Export-Certificate -Cert $cert -FilePath $certPath 2>$null | Out-Null
certutil -addstore Root $certPath 2>$null | Out-Null

if (Get-Command signtool.exe -ErrorAction SilentlyContinue) {
    signtool sign /v /fd SHA256 /sha1 $cert.Thumbprint $SysPath 2>&1 | Out-Null
    Write-Host "[✓] Signed with signtool" -Foreground Green
} else {
    Set-AuthenticodeSignature -FilePath $SysPath -Certificate $cert 2>$null | Out-Null
    Write-Host "[✓] Signed with PowerShell" -Foreground Green
}

# ── 3. Driver service ──────────────────────────────────────────────
Write-Host "[3/5] Installing driver service..." -Foreground Yellow
sc.exe stop pyav 2>$null | Out-Null
sc.exe delete pyav 2>$null | Out-Null
Start-Sleep 0.5
# start= auto：SCM 每次开机自动加载驱动（登录前 ring0 防护就位）
sc.exe create pyav type= kernel start= auto binPath= $SysPath 2>&1 | Out-Null
$startResult = sc.exe start pyav 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[✓] Driver loaded: $SysPath" -Foreground Green
} else {
    Write-Host "[FAIL] Driver failed to start:" -Foreground Red
    Write-Host $startResult -Foreground Red
    Write-Host "       Check WinDbg or DbgView for details" -Foreground Yellow
    exit 1
}

# ── 4. Scheduled task (auto-start at login) ────────────────────────
Write-Host "[4/5] Registering auto-start..." -Foreground Yellow

# Build the command: python pyav_client.py --auto-launch pyav_notify.exe
$TaskCmd = "python `"$ClientPath`" --auto-launch `"$ExePath`""

schtasks /create /tn "PYAV" /tr "$TaskCmd" /sc onlogon /rl highest /f 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[✓] Scheduled task created: PYAV (triggers at login)" -Foreground Green
} else {
    Write-Host "[!] Failed to create scheduled task — run as Admin" -Foreground Yellow
}

# ── 5. Test connection ─────────────────────────────────────────────
Write-Host "[5/5] Testing IOCTL connection..." -Foreground Yellow
$testResult = python -c "
import sys; sys.path.insert(0, '$ProjectRoot')
from pyav_client import PyavClient
try:
    with PyavClient() as c:
        v = c.get_version()
        print(f'OK v{v.major}.{v.minor}.{v.patch}')
except Exception as e:
    print(f'FAIL {e}')
" 2>&1

if ($testResult -match "^OK") {
    Write-Host "[✓] IOCTL test passed — driver communicating" -Foreground Green
} else {
    Write-Host "[!] IOCTL test failed:" -Foreground Yellow
    Write-Host "    $testResult" -Foreground Yellow
}

# ── Summary ─────────────────────────────────────────────────────────
Write-Host @"

╔═══════════════════════════════════════╗
║         PYAV Installation Complete    ║
╠═══════════════════════════════════════╣
║  pyav_kernel.sys  →  Kernel service  ║
║  pyav_notify.exe  →  Notification    ║
║  pyav_client.py   →  IOCTL client    ║
║  Scheduled task   →  Login auto-start║
║                                      ║
║  Logs: WinDbg / DbgView              ║
║  Test: python pyav_client.py         ║
╚═══════════════════════════════════════╝
"@ -Foreground Cyan

# Manual start test
Write-Host "Starting client now..." -Foreground Yellow
& python "$ClientPath" --auto-launch "$ExePath"
