$ErrorActionPreference = "SilentlyContinue"

$installDir = Join-Path $env:LOCALAPPDATA "AlmdinaScannerBridge"
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
    & netsh http delete urlacl url=http://127.0.0.1:17654/ | Out-Null
}

Write-Host "تمت إزالة Almdina Scanner Bridge." -ForegroundColor Green
