
# PYAV — One-shot VM driver test setup
# Run as Administrator on the VM.
# Prerequisites: test signing enabled (bcdedit /set testsigning on → reboot)

$ErrorActionPreference = "Stop"
$DriverPath = Join-Path $PSScriptRoot "out\build\x64-Debug\pyav_kernel.sys"
$ServiceName = "pyav"

Write-Host "=== PYAV Kernel Driver — VM Test Setup ===" -ForegroundColor Cyan

# 1. Check admin
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "ERROR: Run as Administrator!" -ForegroundColor Red
    exit 1
}

# 2. Check driver file
if (-NOT (Test-Path $DriverPath)) {
    Write-Host "ERROR: Driver not found at $DriverPath" -ForegroundColor Red
    Write-Host "Build first: cmake --build out/build/x64-Debug"
    exit 1
}
Write-Host "[✓] Driver found: $DriverPath" -ForegroundColor Green

# 3. Test-sign the driver (PowerShell native — no SDK needed)
Write-Host "[*] Test-signing driver..."
$cert = New-SelfSignedCertificate -Subject "CN=PYAV" -Type CodeSigningCert `
    -CertStoreLocation "Cert:\CurrentUser\My" -KeyUsage DigitalSignature
$certPath = Join-Path $env:TEMP "pyav_test.cer"
Export-Certificate -Cert $cert -FilePath $certPath | Out-Null
certutil -addstore Root $certPath 2>$null | Out-Null

# Try signtool first, fall back to Set-AuthenticodeSignature
if (Get-Command signtool.exe -ErrorAction SilentlyContinue) {
    signtool sign /v /fd SHA256 /sha1 $cert.Thumbprint $DriverPath 2>&1 | Out-Null
} else {
    Set-AuthenticodeSignature -FilePath $DriverPath -Certificate $cert | Out-Null
}
Write-Host "[✓] Driver test-signed" -ForegroundColor Green

# 1.5 Test-signing check
$ts = (bcdedit /enum | Select-String "testsigning").ToString()
if ($ts -match "Yes") {
    Write-Host "[✓] Test signing ON" -ForegroundColor Green
} else {
    Write-Host "[!] Test signing OFF — run and reboot:" -ForegroundColor Yellow
    Write-Host "    bcdedit /set testsigning on"
    Write-Host "    shutdown /r /t 0"
    exit 1
}

# 4. Stop + delete any leftover service (kernel svc not visible to Get-Service)
Write-Host "[*] Cleaning up previous service..."
sc.exe stop  $ServiceName 2>$null | Out-Null
sc.exe delete $ServiceName 2>$null | Out-Null
Start-Sleep 1

# 5. Create and start service
Write-Host "[*] Creating kernel service..."
sc.exe create $ServiceName type= kernel binPath= $DriverPath 2>&1 | Out-Null
Write-Host "[*] Starting driver..."
sc.exe start $ServiceName

Write-Host "[✓] Driver loaded. Check DbgView for [PYAV] output." -ForegroundColor Green
Write-Host ""

# 6. Run Python client test
$pyClient = Join-Path $PSScriptRoot "pyav_client.py"
if (Test-Path $pyClient) {
    Write-Host "[*] Running pyav_client..." -ForegroundColor Cyan
    python $pyClient
} else {
    Write-Host "[!] pyav_client.py not found, skipping test" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Cleanup ===" -ForegroundColor Cyan
Write-Host "  sc stop $ServiceName"
Write-Host "  sc delete $ServiceName"
Write-Host ""
Write-Host "To view debug output: install DbgView (Sysinternals) → Capture → Capture Kernel"
