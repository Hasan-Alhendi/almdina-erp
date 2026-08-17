$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "يجب تشغيل install.ps1 بواسطة Run as administrator." -ForegroundColor Yellow
    exit 1
}

$sourceBridge = Join-Path $PSScriptRoot "AlmdinaScannerBridge.ps1"
$sourceConfig = Join-Path $PSScriptRoot "config.example.json"
if (-not (Test-Path $sourceBridge)) { throw "AlmdinaScannerBridge.ps1 not found." }

$installDir = Join-Path $env:LOCALAPPDATA "AlmdinaScannerBridge"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -Force $sourceBridge (Join-Path $installDir "AlmdinaScannerBridge.ps1")

$configPath = Join-Path $installDir "config.json"
if (-not (Test-Path $configPath)) {
    Copy-Item -Force $sourceConfig $configPath
}

$prefix = "http://127.0.0.1:17654/"
& netsh http delete urlacl url=$prefix 2>$null | Out-Null
& netsh http add urlacl url=$prefix user="$env:USERDOMAIN\$env:USERNAME" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "تعذر حجز عنوان Scanner Bridge في Windows HTTP Service." }

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Almdina Scanner Bridge.lnk"
$targetScript = Join-Path $installDir "AlmdinaScannerBridge.ps1"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$targetScript`""
$shortcut.WorkingDirectory = $installDir
$shortcut.Save()

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*AlmdinaScannerBridge.ps1*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Process -WindowStyle Hidden -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$targetScript`""
)

Start-Sleep -Milliseconds 800
try {
    $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:17654/health" -Headers @{ "X-Almdina-Scanner-Bridge" = "1" } -TimeoutSec 3
    if (-not $health.ok) { throw "Health check failed." }
    Write-Host "تم تثبيت وتشغيل Almdina Scanner Bridge بنجاح." -ForegroundColor Green
    Write-Host "العنوان المحلي: http://127.0.0.1:17654/"
}
catch {
    Write-Host "تم التثبيت لكن فحص التشغيل لم ينجح: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "جرّب تشغيل AlmdinaScannerBridge.ps1 يدويًا لمعرفة الخطأ."
    exit 2
}
