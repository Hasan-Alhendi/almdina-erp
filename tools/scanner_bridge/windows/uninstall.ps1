$ErrorActionPreference = "SilentlyContinue"

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

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Almdina Scanner Bridge.lnk"

Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
    Where-Object { $_.CommandLine -like "*AlmdinaScannerBridge.ps1*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Remove-Item -Force $shortcutPath
Remove-Item -Recurse -Force $installDir

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    & netsh http delete urlacl url="http://127.0.0.1:$port/" | Out-Null
}

Write-Host "تمت إزالة Almdina Scanner Bridge." -ForegroundColor Green
