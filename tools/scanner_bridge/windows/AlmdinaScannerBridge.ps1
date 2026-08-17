param(
    [string]$ConfigPath = "$PSScriptRoot\config.json"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$DefaultPort = 17654
$DefaultMaxScanBytes = 16 * 1024 * 1024
$MaxRequestBytes = 16 * 1024
$DefaultOrigins = @(
    "https://almadina-2.horizontechco.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
)

function Normalize-Origin {
    param([string]$Origin)
    $value = [string]$Origin
    $value = $value.Trim().TrimEnd('/')
    if (-not $value) { return $null }
    if ($value -eq "*") { throw "Wildcard origins are not allowed." }
    if ($value -notmatch '^https?://[^/]+(?::\d+)?$') {
        throw "Invalid allowed origin: $value"
    }
    return $value
}

function Read-BridgeConfig {
    $port = $DefaultPort
    $maxScanBytes = $DefaultMaxScanBytes
    $origins = $DefaultOrigins

    if (Test-Path $ConfigPath) {
        $raw = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
        if ($raw.port) { $port = [int]$raw.port }
        if ($raw.maxScanBytes) { $maxScanBytes = [int64]$raw.maxScanBytes }
        if ($raw.allowedOrigins) { $origins = @($raw.allowedOrigins) }
    }

    if ($port -lt 1024 -or $port -gt 65535) {
        throw "Scanner Bridge port must be between 1024 and 65535."
    }
    if ($maxScanBytes -lt 1048576 -or $maxScanBytes -gt 33554432) {
        throw "maxScanBytes must be between 1 MB and 32 MB."
    }

    $normalizedOrigins = @()
    foreach ($origin in $origins) {
        $normalized = Normalize-Origin -Origin ([string]$origin)
        if ($normalized -and $normalizedOrigins -notcontains $normalized) {
            $normalizedOrigins += $normalized
        }
    }
    if (-not $normalizedOrigins.Count) {
        throw "At least one allowed origin is required."
    }

    return [pscustomobject]@{
        Port = $port
        MaxScanBytes = $maxScanBytes
        AllowedOrigins = $normalizedOrigins
    }
}

function Set-SecurityHeaders {
    param($Context)
    $Context.Response.Headers["Cache-Control"] = "no-store"
    $Context.Response.Headers["X-Content-Type-Options"] = "nosniff"
}

function Write-JsonResponse {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Payload,
        [int]$StatusCode = 200
    )
    $json = $Payload | ConvertTo-Json -Depth 8 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    Set-SecurityHeaders -Context $Context
    $Context.Response.StatusCode = $StatusCode
    $Context.Response.ContentType = "application/json; charset=utf-8"
    $Context.Response.ContentLength64 = $bytes.Length
    $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    $Context.Response.OutputStream.Close()
}

function Add-CorsHeaders {
    param($Context, [string[]]$AllowedOrigins)
    $origin = ([string]$Context.Request.Headers["Origin"]).TrimEnd('/')
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
    if ($Request.ContentLength64 -gt $MaxRequestBytes) {
        throw "Scanner request body is too large."
    }
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
                # WIA device type 1 = ScannerDeviceType.
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
        throw "تعذر الوصول إلى WIA في Windows. تأكد من تثبيت تعريف السكانر وتشغيل خدمة Windows Image Acquisition (WIA)."
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
            if (-not $jpegCodec) { throw "JPEG encoder is unavailable on this Windows installation." }

            $encoderParameters = New-Object System.Drawing.Imaging.EncoderParameters(1)
            $qualityParameter = New-Object System.Drawing.Imaging.EncoderParameter(
                [System.Drawing.Imaging.Encoder]::Quality,
                [long]92
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
    param($Options, [int64]$MaxScanBytes)

    $scannerCount = Get-WiaScannerCount
    if ($scannerCount -lt 1) {
        throw "لا يوجد سكانر معرّف في Windows عبر WIA. ثبّت تعريف الجهاز وتأكد أنه يظهر في Windows ثم أعد المحاولة."
    }

    $requestedDpi = 300
    if ($Options.dpi) {
        $requestedDpi = [Math]::Max(75, [Math]::Min(1200, [int]$Options.dpi))
    }

    $dialog = New-Object -ComObject WIA.CommonDialog
    $image = $null
    try {
        # Native WIA UI handles device selection and vendor-specific settings.
        $image = $dialog.ShowAcquireImage()
        if (-not $image) {
            throw "تم إلغاء عملية المسح أو لم يرجع السكانر صورة."
        }

        $bytes = Convert-WiaImageToJpeg -WiaImage $image
        if ($bytes.LongLength -gt $MaxScanBytes) {
            throw "صورة السكانر أكبر من الحد المسموح. خفّض DPI أو مساحة المسح ثم أعد المحاولة."
        }

        $actualDpi = $requestedDpi
        try {
            if ([double]$image.HorizontalResolution -gt 0) {
                $actualDpi = [int][Math]::Round([double]$image.HorizontalResolution)
            }
        }
        catch {}

        return [pscustomobject]@{
            Bytes = $bytes
            MimeType = "image/jpeg"
            Filename = "scanner-$([DateTime]::Now.ToString('yyyyMMdd-HHmmss')).jpg"
            Device = "WIA Scanner"
            Dpi = $actualDpi
        }
    }
    finally {
        if ($image) {
            try { [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($image) } catch {}
        }
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
            if (-not [System.Net.IPAddress]::IsLoopback($context.Request.RemoteEndPoint.Address)) {
                Write-JsonResponse -Context $context -StatusCode 403 -Payload @{ ok = $false; message = "Loopback requests only." }
                continue
            }

            if (-not (Add-CorsHeaders -Context $context -AllowedOrigins $config.AllowedOrigins)) {
                Write-JsonResponse -Context $context -StatusCode 403 -Payload @{ ok = $false; message = "Origin is not allowed by Almdina Scanner Bridge." }
                continue
            }

            if ($context.Request.HttpMethod -eq "OPTIONS") {
                Set-SecurityHeaders -Context $context
                $context.Response.StatusCode = 204
                $context.Response.Close()
                continue
            }

            if ([string]$context.Request.Headers["X-Almdina-Scanner-Bridge"] -ne "1") {
                Write-JsonResponse -Context $context -StatusCode 400 -Payload @{ ok = $false; message = "Missing scanner bridge request header." }
                continue
            }

            $path = $context.Request.Url.AbsolutePath
            if ($context.Request.HttpMethod -eq "GET" -and $path -eq "/health") {
                $scannerCount = Get-WiaScannerCount
                Write-JsonResponse -Context $context -Payload @{
                    ok = $true
                    version = "2.0.0"
                    provider = "wia"
                    device_count = $scannerCount
                    ready = ($scannerCount -gt 0)
                }
                continue
            }

            if ($context.Request.HttpMethod -eq "POST" -and $path -eq "/scan") {
                $options = Read-RequestJson -Request $context.Request
                $scan = Acquire-ScannerImage -Options $options -MaxScanBytes $config.MaxScanBytes
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

            Write-JsonResponse -Context $context -StatusCode 404 -Payload @{ ok = $false; message = "Unknown scanner bridge endpoint." }
        }
        catch {
            try {
                Write-JsonResponse -Context $context -StatusCode 500 -Payload @{ ok = $false; message = [string]$_.Exception.Message }
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
