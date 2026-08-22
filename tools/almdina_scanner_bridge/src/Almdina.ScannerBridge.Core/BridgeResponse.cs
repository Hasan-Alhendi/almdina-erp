using System.Text;
using System.Text.Json;

namespace Almdina.ScannerBridge.Core;

public sealed class BridgeResponse
{
    private BridgeResponse(int statusCode, string? contentType, byte[] body, IReadOnlyDictionary<string, string>? headers = null)
    {
        StatusCode = statusCode;
        ContentType = contentType;
        Body = body;
        Headers = headers ?? new Dictionary<string, string>();
    }

    public int StatusCode { get; }

    public string? ContentType { get; }

    public byte[] Body { get; }

    public IReadOnlyDictionary<string, string> Headers { get; }

    public BridgeResponse WithHeaders(IReadOnlyDictionary<string, string> headers) =>
        new(StatusCode, ContentType, Body, headers);

    public static BridgeResponse Empty(int statusCode) => new(statusCode, null, []);

    public static BridgeResponse Jpeg(byte[] bytes) => new(200, "image/jpeg", bytes);

    public static BridgeResponse Json(int statusCode, object payload)
    {
        var json = JsonSerializer.Serialize(payload, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        });
        return new BridgeResponse(statusCode, "application/json; charset=utf-8", Encoding.UTF8.GetBytes(json));
    }
}
