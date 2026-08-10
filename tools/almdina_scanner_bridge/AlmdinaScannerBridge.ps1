param(
    [int]$Port = 17831,
    [string[]]$AllowedOrigins = @(
        "https://almadina-2.horizontechco.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$JpegFormatId = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}"
$Prefix = "http://127.0.0.1:$Port/"
$Listener = [System.Net.HttpListener]::new()
$Listener.Prefixes.Add($Prefix)

function Write-JsonResponse {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [int]$StatusCode = 200,
        [Parameter(Mandatory = $true)]$Payload
    )
    $Json = $Payload | ConvertTo-Json -Compress -Depth 5
    $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Json)
    $Context.Response.StatusCode = $StatusCode
    $Context.Response.ContentType = "application/json; charset=utf-8"
    $Context.Response.ContentLength64 = $Bytes.Length
    $Context.Response.OutputStream.Write($Bytes, 0, $Bytes.Length)
}

function Set-CorsHeaders {
    param([Parameter(Mandatory = $true)]$Context)
    $Origin = [string]$Context.Request.Headers["Origin"]
    if ([string]::IsNullOrWhiteSpace($Origin)) {
        return $true
    }
    if ($AllowedOrigins -notcontains $Origin) {
        Write-JsonResponse -Context $Context -StatusCode 403 -Payload @{
            ok = $false
            message = "Origin is not allowed to use the scanner bridge."
        }
        return $false
    }
    $Context.Response.Headers["Access-Control-Allow-Origin"] = $Origin
    $Context.Response.Headers["Vary"] = "Origin"
    $Context.Response.Headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    $Context.Response.Headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
    $Context.Response.Headers["Access-Control-Allow-Private-Network"] = "true"
    return $true
}

function Acquire-ScannerImage {
    $Dialog = New-Object -ComObject "WIA.CommonDialog"
    # Scanner device, unspecified intent/bias, JPEG output, always show the
    # Windows device selector and common scan UI. Cancel returns $null.
    return $Dialog.ShowAcquireImage(1, 0, 0, $JpegFormatId, $true, $true, $false)
}

function Write-ImageResponse {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)]$Image
    )
    $TempPath = Join-Path $env:TEMP ("almadina-scan-{0}.jpg" -f [Guid]::NewGuid().ToString("N"))
    try {
        $Image.SaveFile($TempPath)
        $Bytes = [System.IO.File]::ReadAllBytes($TempPath)
        $Context.Response.StatusCode = 200
        $Context.Response.ContentType = "image/jpeg"
        $Context.Response.ContentLength64 = $Bytes.Length
        $Context.Response.OutputStream.Write($Bytes, 0, $Bytes.Length)
    }
    finally {
        if (Test-Path $TempPath) {
            Remove-Item $TempPath -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    $Listener.Start()
}
catch {
    Write-Host "Unable to start Almdina Scanner Bridge on $Prefix" -ForegroundColor Red
    Write-Host "Run PowerShell as Administrator once and reserve the URL with:" -ForegroundColor Yellow
    Write-Host "  netsh http add urlacl url=$Prefix user=$env:USERNAME" -ForegroundColor Cyan
    throw
}

Write-Host "Almdina Scanner Bridge is running on $Prefix" -ForegroundColor Green
Write-Host "Keep this window open while using Scan from printer in Almdina ERP." -ForegroundColor DarkGray

try {
    while ($Listener.IsListening) {
        $Context = $Listener.GetContext()
        try {
            if (-not (Set-CorsHeaders -Context $Context)) {
                continue
            }

            if ($Context.Request.HttpMethod -eq "OPTIONS") {
                $Context.Response.StatusCode = 204
                continue
            }

            $Path = $Context.Request.Url.AbsolutePath.TrimEnd("/")
            if ($Path -eq "/health" -and $Context.Request.HttpMethod -eq "GET") {
                Write-JsonResponse -Context $Context -Payload @{
                    ok = $true
                    service = "almadina-scanner-bridge"
                    version = "1.0.0"
                }
                continue
            }

            if ($Path -eq "/scan" -and $Context.Request.HttpMethod -eq "POST") {
                try {
                    $Image = Acquire-ScannerImage
                    if ($null -eq $Image) {
                        $Context.Response.StatusCode = 204
                    }
                    else {
                        Write-ImageResponse -Context $Context -Image $Image
                    }
                }
                catch {
                    Write-JsonResponse -Context $Context -StatusCode 500 -Payload @{
                        ok = $false
                        message = "Scanner acquisition failed. Check that Windows can see the scanner and try again."
                    }
                }
                continue
            }

            Write-JsonResponse -Context $Context -StatusCode 404 -Payload @{
                ok = $false
                message = "Not found."
            }
        }
        finally {
            try { $Context.Response.OutputStream.Close() } catch { }
            try { $Context.Response.Close() } catch { }
        }
    }
}
finally {
    if ($Listener.IsListening) { $Listener.Stop() }
    $Listener.Close()
}
