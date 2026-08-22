namespace Almdina.ScannerBridge.Core;

public sealed class BridgeRequest
{
    private readonly IReadOnlyDictionary<string, string> _headers;

    public BridgeRequest(string method, string path, IEnumerable<KeyValuePair<string, string>>? headers = null)
    {
        Method = string.IsNullOrWhiteSpace(method) ? throw new ArgumentException("Method is required.", nameof(method)) : method.ToUpperInvariant();
        Path = string.IsNullOrWhiteSpace(path) || !path.StartsWith('/') ? throw new ArgumentException("Absolute path is required.", nameof(path)) : path;
        _headers = new Dictionary<string, string>(headers ?? [], StringComparer.OrdinalIgnoreCase);
    }

    public string Method { get; }

    public string Path { get; }

    public string? Header(string name) => _headers.TryGetValue(name, out var value) ? value : null;
}
