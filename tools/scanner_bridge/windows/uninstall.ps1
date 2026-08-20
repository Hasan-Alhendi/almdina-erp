$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "يجب تشغيل uninstall.ps1 بواسطة Run as administrator." -ForegroundColor Yellow
    exit 1
}

$installDir = Join-Path $env:LOCALAPPDATA "AlmdinaScannerBridge"
$configPath = Join-Path $installDir "config.json"
$port = 17654
if (Test-Path $configPath) {
    try {
        $config = Get-Content -Raw -Path $configPath | ConvertFrom-Json
        if ($config.port) { $port = [int]$config.port }
    }
    catch {}
}

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*AlmdinaScannerBridge.ps1*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Almdina Scanner Bridge.lnk"
Remove-Item -Force -ErrorAction SilentlyContinue $shortcutPath

$prefix = "http://127.0.0.1:$port/"
& netsh http delete urlacl url=$prefix 2>$null | Out-Null

if (Test-Path $installDir) {
    Remove-Item -Recurse -Force $installDir
}

Write-Host "تم حذف Almdina Scanner Bridge من هذا الجهاز." -ForegroundColor Green
