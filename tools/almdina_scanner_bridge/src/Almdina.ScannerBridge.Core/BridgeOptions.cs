namespace Almdina.ScannerBridge.Core;

public sealed class BridgeOptions
{
    public const int DefaultPort = 17831;
    public const int MaxImageBytes = 8 * 1024 * 1024;

    private static readonly string[] DefaultAllowedOrigins =
    [
        "https://almadina-2.horizontechco.com",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ];

    public BridgeOptions(int port = DefaultPort, IEnumerable<string>? allowedOrigins = null)
    {
        if (port is < 1 or > 65535)
        {
            throw new ArgumentOutOfRangeException(nameof(port));
        }

        Port = port;
        AllowedOrigins = (allowedOrigins ?? DefaultAllowedOrigins).ToArray();
        if (AllowedOrigins.Count == 0)
        {
            throw new ArgumentException("At least one allowed origin is required.", nameof(allowedOrigins));
        }
    }

    public int Port { get; }

    public IReadOnlyList<string> AllowedOrigins { get; }
}
