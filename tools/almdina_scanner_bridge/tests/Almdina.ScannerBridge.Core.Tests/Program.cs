using Almdina.ScannerBridge.Core;
using System.Text;

var tests = new (string Name, Func<Task> Run)[]
{
    ("health without browser origin", HealthWithoutOrigin),
    ("default production origins allow scanning", DefaultProductionOriginsAllowScanning),
    ("allowed CORS health", AllowedCorsHealth),
    ("forbidden browser origin", ForbiddenOrigin),
    ("private-network preflight", PrivateNetworkPreflight),
    ("scan requires browser origin", ScanRequiresOrigin),
    ("successful JPEG scan", SuccessfulScan),
    ("cancelled scan", CancelledScan),
    ("busy scanner", BusyScanner),
    ("oversized scanner image", OversizedImage),
    ("invalid image payload", InvalidImage),
};

var failures = new List<string>();
foreach (var (name, run) in tests)
{
    try
    {
        await run();
        Console.WriteLine($"PASS {name}");
    }
    catch (Exception error)
    {
        failures.Add($"FAIL {name}: {error.Message}");
        Console.Error.WriteLine(failures[^1]);
    }
}

if (failures.Count > 0)
{
    Environment.ExitCode = 1;
}

return;

static BridgeRequestDispatcher Dispatcher(IScanner scanner) =>
    new(scanner, new BridgeOptions(allowedOrigins: [TestData.AllowedOrigin]), "2.2.0-test");

static BridgeRequestDispatcher DefaultDispatcher(IScanner scanner) =>
    new(scanner, new BridgeOptions(), "2.2.0-test");

static BridgeRequest Request(string method, string path, string? origin = null)
{
    IEnumerable<KeyValuePair<string, string>> headers = origin is null
        ? Array.Empty<KeyValuePair<string, string>>()
        : [new KeyValuePair<string, string>("Origin", origin)];
    return new BridgeRequest(method, path, headers);
}

static async Task HealthWithoutOrigin()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("GET", "/health"), CancellationToken.None);
    Equal(200, response.StatusCode);
    Contains("\"service\":\"almadina-scanner-bridge\"", response.Body);
    Contains("\"startup\":\"windows-login\"", response.Body);
    Equal("no-store", response.Headers["Cache-Control"]);
    False(response.Headers.ContainsKey("Access-Control-Allow-Origin"), "Address-bar diagnostics must not invent an origin.");
}

static async Task DefaultProductionOriginsAllowScanning()
{
    var dispatcher = DefaultDispatcher(FakeScanner.Success());
    foreach (var origin in TestData.ProductionOrigins)
    {
        var response = await dispatcher.DispatchAsync(Request("OPTIONS", "/scan", origin), CancellationToken.None);
        Equal(204, response.StatusCode);
        Equal(origin, response.Headers["Access-Control-Allow-Origin"]);
        Equal("true", response.Headers["Access-Control-Allow-Private-Network"]);
    }

    foreach (var origin in TestData.ForbiddenOrigins)
    {
        var response = await dispatcher.DispatchAsync(Request("POST", "/scan", origin), CancellationToken.None);
        Equal(403, response.StatusCode);
        False(response.Headers.ContainsKey("Access-Control-Allow-Origin"), $"Forbidden origin '{origin}' must not receive CORS permission.");
    }
}

static async Task AllowedCorsHealth()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("GET", "/health/", TestData.AllowedOrigin), CancellationToken.None);
    Equal(200, response.StatusCode);
    Equal(TestData.AllowedOrigin, response.Headers["Access-Control-Allow-Origin"]);
}

static async Task ForbiddenOrigin()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("GET", "/health", "https://evil.example"), CancellationToken.None);
    Equal(403, response.StatusCode);
    False(response.Headers.ContainsKey("Access-Control-Allow-Origin"), "A forbidden origin must not receive CORS permission.");
}

static async Task PrivateNetworkPreflight()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("OPTIONS", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(204, response.StatusCode);
    Equal("true", response.Headers["Access-Control-Allow-Private-Network"]);
    Equal(0, response.Body.Length);
}

static async Task ScanRequiresOrigin()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("POST", "/scan"), CancellationToken.None);
    Equal(403, response.StatusCode);
}

static async Task SuccessfulScan()
{
    var response = await Dispatcher(FakeScanner.Success()).DispatchAsync(Request("POST", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(200, response.StatusCode);
    Equal("image/jpeg", response.ContentType);
    Equal(TestData.AllowedOrigin, response.Headers["Access-Control-Allow-Origin"]);
    True(response.Body.AsSpan(0, 3).SequenceEqual(new byte[] { 0xff, 0xd8, 0xff }), "Expected JPEG signature.");
}

static async Task CancelledScan()
{
    var response = await Dispatcher(FakeScanner.Cancel()).DispatchAsync(Request("POST", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(204, response.StatusCode);
    Equal(0, response.Body.Length);
}

static async Task BusyScanner()
{
    var response = await Dispatcher(FakeScanner.Throw(new ScannerBusyException())).DispatchAsync(Request("POST", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(409, response.StatusCode);
    Contains("scanner_busy", response.Body);
}

static async Task OversizedImage()
{
    var bytes = new byte[BridgeOptions.MaxImageBytes + 1];
    bytes[0] = 0xff; bytes[1] = 0xd8; bytes[2] = 0xff;
    var response = await Dispatcher(FakeScanner.Success(bytes)).DispatchAsync(Request("POST", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(413, response.StatusCode);
    Contains("image_too_large", response.Body);
}

static async Task InvalidImage()
{
    var response = await Dispatcher(FakeScanner.Success(Encoding.UTF8.GetBytes("not-jpeg"))).DispatchAsync(Request("POST", "/scan", TestData.AllowedOrigin), CancellationToken.None);
    Equal(500, response.StatusCode);
    Contains("invalid_scanner_image", response.Body);
}

static void Equal<T>(T expected, T actual)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
    {
        throw new InvalidOperationException($"Expected '{expected}', got '{actual}'.");
    }
}

static void True(bool value, string message)
{
    if (!value) throw new InvalidOperationException(message);
}

static void False(bool value, string message) => True(!value, message);

static void Contains(string expected, byte[] actual)
{
    if (!Encoding.UTF8.GetString(actual).Contains(expected, StringComparison.Ordinal))
    {
        throw new InvalidOperationException($"Response did not contain '{expected}'.");
    }
}

internal sealed class FakeScanner : IScanner
{
    private readonly Func<ScanOutcome> _acquire;

    private FakeScanner(Func<ScanOutcome> acquire) => _acquire = acquire;

    public Task<ScanOutcome> AcquireJpegAsync(CancellationToken cancellationToken) => Task.FromResult(_acquire());

    public static FakeScanner Success(byte[]? bytes = null) => new(() => ScanOutcome.Success(bytes ?? [0xff, 0xd8, 0xff, 0x01]));

    public static FakeScanner Cancel() => new(ScanOutcome.Cancel);

    public static FakeScanner Throw(Exception error) => new(() => throw error);
}

internal static class TestData
{
    public const string AllowedOrigin = "https://almadina-2.horizontechco.com";

    public static readonly string[] ProductionOrigins =
    [
        AllowedOrigin,
        "https://almadina-b2.horizontechco.com",
        "https://almadina.horizontechco.com",
    ];

    public static readonly string[] ForbiddenOrigins =
    [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://evil.example",
    ];
}
