param(
    [string]$ConfigPath = "$PSScriptRoot\config.json"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$DefaultPort = 17654
$DefaultOrigins = @(
    "https://almadina-2.horizontechco.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
)

function Read-BridgeConfig {
    if (Test-Path $ConfigPath) {
        $raw = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        $port = if ($raw.port) { [int]$raw.port } else { $DefaultPort }
        if ($port -lt 1024 -or $port -gt 65535) {
            throw "Scanner Bridge port must be between 1024 and 65535."
        }
        $origins = @($raw.allowedOrigins | ForEach-Object { [string]$_ })
        if (-not $origins.Count) { $origins = $DefaultOrigins }
        return [pscustomobject]@{ Port = $port; AllowedOrigins = $origins }
    }
    return [pscustomobject]@{ Port = $DefaultPort; AllowedOrigins = $DefaultOrigins }
}

function Write-JsonResponse {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Payload,
        [int]$StatusCode = 200
    )
    $json = $Payload | ConvertTo-Json -Depth 8 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $Context.Response.StatusCode = $StatusCode
    $Context.Response.ContentType = "application/json; charset=utf-8"
    $Context.Response.ContentLength64 = $bytes.Length
    $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Context.Response.OutputStream.Close()
}

function Add-CorsHeaders {
    param($Context, [string[]]$AllowedOrigins)
    $origin = [string]$Context.Request.Headers["Origin"]
    if (-not $origin) { return $true }
    if ($AllowedOrigins -notcontains $origin) { return $false }
    $Context.Response.Headers["Access-Control-Allow-Origin"] = $origin
    $Context.Response.Headers["Vary"] = "Origin"
    $Context.Response.Headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    $Context.Response.Headers["Access-Control-Allow-Headers"] = "Content-Type, X-Almdina-Scanner-Bridge"
    $Context.Response.Headers["Access-Control-Max-Age"] = "600"
    $Context.Response.Headers["Access-Control-Allow-Private-Network"] = "true"
    return $true
}

function Read-RequestJson {
    param($Request)
    if (-not $Request.HasEntityBody) { return @{} }
    $reader = New-Object System.IO.StreamReader($Request.InputStream, $Request.ContentEncoding)
    try {
        $body = $reader.ReadToEnd()
    }
    finally {
        $reader.Dispose()
    }
    if (-not $body) { return @{} }
    return $body | ConvertFrom-Json
}

function Get-WiaScannerCount {
    $manager = $null
    try {
        $manager = New-Object -ComObject WIA.DeviceManager
        $count = 0
        foreach ($deviceInfo in $manager.DeviceInfos) {
            try {
                # WIA device type 1 is ScannerDeviceType.
                if ([int]$deviceInfo.Type -eq 1) { $count += 1 }
            }
            finally {
                if ($deviceInfo) {
                    try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($deviceInfo) } catch {}
                }
            }
        }
        return $count
    }
    catch {
        # WIA itself being unavailable is different from having zero scanners.
        throw "تعذر الوصول إلى خدمة WIA في Windows. تأكد من تثبيت تعريف الـScanner وتشغيل Windows Image Acquisition (WIA)."
    }
    finally {
        if ($manager) {
            try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($manager) } catch {}
        }
    }
}

function Convert-WiaImageToJpeg {
    param($WiaImage)
    $id = [guid]::NewGuid().ToString("N")
    $extension = [string]$WiaImage.FileExtension
    if (-not $extension) { $extension = "bmp" }
    $rawPath = Join-Path ([System.IO.Path]::GetTempPath()) "almdina-scan-$id.$extension"
    $jpegPath = Join-Path ([System.IO.Path]::GetTempPath()) "almdina-scan-$id.jpg"
    try {
        $WiaImage.SaveFile($rawPath)
        $source = [System.Drawing.Image]::FromFile($rawPath)
        try {
            $jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
                Where-Object { $_.MimeType -eq "image/jpeg" } |
                Select-Object -First 1
            $encoderParameters = New-Object System.Drawing.Imaging.EncoderParameters(1)
            $qualityParameter = New-Object System.Drawing.Imaging.EncoderParameter(
                [System.Drawing.Imaging.Encoder]::Quality,
                [long]94
            )
            $encoderParameters.Param[0] = $qualityParameter
            try {
                $source.Save($jpegPath, $jpegCodec, $encoderParameters)
            }
            finally {
                $qualityParameter.Dispose()
                $encoderParameters.Dispose()
            }
        }
        finally {
            $source.Dispose()
        }
        return [System.IO.File]::ReadAllBytes($jpegPath)
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $rawPath, $jpegPath
    }
}

function Acquire-ScannerImage {
    param($Options)
    $scannerCount = Get-WiaScannerCount
    if ($scannerCount -lt 1) {
        throw "لا يوجد Scanner معرّف في Windows عبر WIA. ثبّت تعريف الجهاز وتأكد أنه يظهر في إعدادات Windows ثم أعد المحاولة."
    }

    $dialog = New-Object -ComObject WIA.CommonDialog
    try {
        # WIA's native acquisition dialog owns device selection and scanner-specific
        # options. This keeps the bridge generic across printer/scanner models.
        $image = $dialog.ShowAcquireImage()
        if (-not $image) {
            throw "تم إلغاء عملية المسح أو لم يرجع الـScanner صورة."
        }
        $bytes = Convert-WiaImageToJpeg -WiaImage $image
        return [pscustomobject]@{
            Bytes = $bytes
            MimeType = "image/jpeg"
            Filename = "scanner-$([DateTime]::Now.ToString('yyyyMMdd-HHmmss')).jpg"
            Device = "WIA Scanner"
            Dpi = if ($Options.dpi) { [int]$Options.dpi } else { 300 }
        }
    }
    finally {
        if ($dialog) {
            try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($dialog) } catch {}
        }
    }
}

$config = Read-BridgeConfig
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://127.0.0.1:$($config.Port)/")

try {
    $listener.Start()
    Write-Host "Almdina Scanner Bridge listening on http://127.0.0.1:$($config.Port)/"

    while ($listener.IsListening) {
        $context = $listener.GetContext()
        try {
            if (-not (Add-CorsHeaders -Context $context -AllowedOrigins $config.AllowedOrigins)) {
                Write-JsonResponse -Context $context -StatusCode 403 -Payload @{
                    ok = $false
                    message = "Origin is not allowed by Almdina Scanner Bridge."
                }
                continue
            }

            if ($context.Request.HttpMethod -eq "OPTIONS") {
                $context.Response.StatusCode = 204
                $context.Response.Close()
                continue
            }

            if ([string]$context.Request.Headers["X-Almdina-Scanner-Bridge"] -ne "1") {
                Write-JsonResponse -Context $context -StatusCode 400 -Payload @{
                    ok = $false
                    message = "Missing scanner bridge request header."
                }
                continue
            }

            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/health") {
                $scannerCount = Get-WiaScannerCount
                Write-JsonResponse -Context $context -Payload @{
                    ok = $true
                    version = "1.1.0"
                    provider = "wia"
                    device_count = $scannerCount
                    ready = ($scannerCount -gt 0)
                }
                continue
            }

            if ($context.Request.HttpMethod -eq "POST" -and $path -eq "/scan") {
                $options = Read-RequestJson -Request $context.Request
                $scan = Acquire-ScannerImage -Options $options
                Write-JsonResponse -Context $context -Payload @{
                    ok = $true
                    provider = "local-wia-bridge"
                    device = $scan.Device
                    dpi = $scan.Dpi
                    mime_type = $scan.MimeType
                    filename = $scan.Filename
                    data_base64 = [Convert]::ToBase64String($scan.Bytes)
                }
                continue
            }

            Write-JsonResponse -Context $context -StatusCode 404 -Payload @{
                ok = $false
                message = "Unknown scanner bridge endpoint."
            }
        }
        catch {
            try {
                Write-JsonResponse -Context $context -StatusCode 500 -Payload @{
                    ok = $false
                    message = [string]$_.Exception.Message
                }
            }
            catch {
                try { $context.Response.Abort() } catch {}
            }
        }
    }
}
finally {
    if ($listener.IsListening) { $listener.Stop() }
    $listener.Close()
}
