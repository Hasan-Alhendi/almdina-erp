namespace Almdina.ScannerBridge.Core;

public sealed class BridgeRequestDispatcher
{
    private readonly IScanner _scanner;
    private readonly OriginPolicy _origins;
    private readonly string _version;

    public BridgeRequestDispatcher(IScanner scanner, BridgeOptions options, string version)
    {
        _scanner = scanner ?? throw new ArgumentNullException(nameof(scanner));
        _origins = new OriginPolicy(options?.AllowedOrigins ?? throw new ArgumentNullException(nameof(options)));
        _version = string.IsNullOrWhiteSpace(version) ? "unknown" : version;
    }

    public async Task<BridgeResponse> DispatchAsync(BridgeRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var path = request.Path.Length > 1 ? request.Path.TrimEnd('/') : request.Path;
        var origin = request.Header("Origin");
        var hasOrigin = !string.IsNullOrWhiteSpace(origin);
        var originAllowed = hasOrigin && _origins.IsAllowed(origin);

        if (hasOrigin && !originAllowed)
        {
            return Secure(BridgeResponse.Json(403, new
            {
                ok = false,
                code = "origin_not_allowed",
                message = "Origin is not allowed to use the scanner bridge.",
            }));
        }

        if (request.Method == "OPTIONS")
        {
            if (!originAllowed || (path != "/health" && path != "/scan"))
            {
                return Secure(BridgeResponse.Json(403, new
                {
                    ok = false,
                    code = "origin_required",
                    message = "An allowed browser origin is required.",
                }));
            }

            return Cors(Secure(BridgeResponse.Empty(204)), origin!);
        }

        if (path == "/health" && request.Method == "GET")
        {
            var response = Secure(BridgeResponse.Json(200, new
            {
                ok = true,
                service = "almadina-scanner-bridge",
                version = _version,
                startup = "windows-login",
            }));
            return originAllowed ? Cors(response, origin!) : response;
        }

        if (path == "/scan" && request.Method == "POST")
        {
            if (!originAllowed)
            {
                return Secure(BridgeResponse.Json(403, new
                {
                    ok = false,
                    code = "origin_required",
                    message = "An allowed browser origin is required for scanning.",
                }));
            }

            return Cors(await ScanAsync(cancellationToken), origin!);
        }

        if (path is "/health" or "/scan")
        {
            return Secure(BridgeResponse.Json(405, new { ok = false, code = "method_not_allowed", message = "Method not allowed." }));
        }

        return Secure(BridgeResponse.Json(404, new { ok = false, code = "not_found", message = "Not found." }));
    }

    private async Task<BridgeResponse> ScanAsync(CancellationToken cancellationToken)
    {
        try
        {
            var result = await _scanner.AcquireJpegAsync(cancellationToken).ConfigureAwait(false);
            if (result.Cancelled)
            {
                return Secure(BridgeResponse.Empty(204));
            }

            var bytes = result.JpegBytes;
            if (bytes is null || bytes.Length < 3 || bytes[0] != 0xff || bytes[1] != 0xd8 || bytes[2] != 0xff)
            {
                return Secure(BridgeResponse.Json(500, new
                {
                    ok = false,
                    code = "invalid_scanner_image",
                    message = "Scanner did not return a valid JPEG image.",
                }));
            }

            if (bytes.Length > BridgeOptions.MaxImageBytes)
            {
                return Secure(BridgeResponse.Json(413, new
                {
                    ok = false,
                    code = "image_too_large",
                    message = "Scanned image exceeds the maximum allowed size.",
                }));
            }

            return Secure(BridgeResponse.Jpeg(bytes));
        }
        catch (ScannerBusyException)
        {
            return Secure(BridgeResponse.Json(409, new { ok = false, code = "scanner_busy", message = "A scan is already in progress." }));
        }
        catch (ScannerUnavailableException)
        {
            return Secure(BridgeResponse.Json(503, new { ok = false, code = "scanner_unavailable", message = "Windows cannot find a compatible scanner." }));
        }
        catch (ScannerAcquisitionException)
        {
            return Secure(BridgeResponse.Json(500, new { ok = false, code = "scan_failed", message = "Scanner acquisition failed." }));
        }
    }

    private static BridgeResponse Secure(BridgeResponse response)
    {
        var headers = new Dictionary<string, string>(response.Headers, StringComparer.OrdinalIgnoreCase)
        {
            ["Cache-Control"] = "no-store",
            ["X-Content-Type-Options"] = "nosniff",
        };
        return response.WithHeaders(headers);
    }

    private static BridgeResponse Cors(BridgeResponse response, string origin)
    {
        var headers = new Dictionary<string, string>(response.Headers, StringComparer.OrdinalIgnoreCase)
        {
            ["Access-Control-Allow-Origin"] = origin,
            ["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS",
            ["Access-Control-Allow-Headers"] = "Content-Type, Accept",
            ["Access-Control-Allow-Private-Network"] = "true",
            ["Vary"] = "Origin",
        };
        return response.WithHeaders(headers);
    }
}
