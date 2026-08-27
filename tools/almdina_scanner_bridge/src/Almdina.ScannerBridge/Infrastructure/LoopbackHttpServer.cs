using Almdina.ScannerBridge.Core;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace Almdina.ScannerBridge.Infrastructure;

internal sealed class LoopbackHttpServer : IDisposable
{
    private const int MaxHeaderBytes = 16 * 1024;
    private static readonly TimeSpan HeaderTimeout = TimeSpan.FromSeconds(5);

    private readonly TcpListener _listener;
    private readonly BridgeRequestDispatcher _dispatcher;
    private readonly FileLogger _logger;
    private readonly CancellationTokenSource _lifetime = new();
    private Task? _acceptLoop;
    private bool _disposed;

    public LoopbackHttpServer(BridgeOptions options, BridgeRequestDispatcher dispatcher, FileLogger logger)
    {
        _listener = new TcpListener(IPAddress.Loopback, options.Port);
        _dispatcher = dispatcher;
        _logger = logger;
    }

    public void Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (_acceptLoop is not null)
        {
            return;
        }

        _listener.Start(backlog: 8);
        _acceptLoop = AcceptLoopAsync(_lifetime.Token);
    }

    private async Task AcceptLoopAsync(CancellationToken cancellationToken)
    {
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                var client = await _listener.AcceptTcpClientAsync(cancellationToken).ConfigureAwait(false);
                _ = HandleClientAsync(client, cancellationToken);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
        catch (ObjectDisposedException) when (cancellationToken.IsCancellationRequested)
        {
        }
        catch (Exception error)
        {
            _logger.Error("Scanner bridge listener stopped unexpectedly.", error);
        }
    }

    private async Task HandleClientAsync(TcpClient client, CancellationToken cancellationToken)
    {
        using (client)
        {
            client.NoDelay = true;
            await using var stream = client.GetStream();
            try
            {
                using var headerTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                headerTimeout.CancelAfter(HeaderTimeout);

                var request = await ReadRequestAsync(stream, headerTimeout.Token).ConfigureAwait(false);
                var response = await _dispatcher.DispatchAsync(request, cancellationToken).ConfigureAwait(false);
                if (string.Equals(request.Method, "POST", StringComparison.Ordinal)
                    && string.Equals(request.Path.TrimEnd('/'), "/scan", StringComparison.Ordinal))
                {
                    _logger.Info(
                        $"Scanner HTTP response {response.StatusCode}, "
                        + $"{response.ContentType ?? "no content type"}, {response.Body.Length} bytes."
                    );
                }
                await WriteResponseAsync(stream, response, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
            }
            catch (InvalidDataException error)
            {
                _logger.Info($"Rejected malformed local request: {error.Message}");
                try
                {
                    await WriteResponseAsync(
                        stream,
                        ErrorResponse(400, "bad_request", "Bad request."),
                        CancellationToken.None
                    ).ConfigureAwait(false);
                }
                catch { }
            }
            catch (Exception error)
            {
                _logger.Error("Local scanner request failed.", error);
                try
                {
                    await WriteResponseAsync(
                        stream,
                        ErrorResponse(500, "internal_error", "Scanner bridge request failed."),
                        CancellationToken.None
                    ).ConfigureAwait(false);
                }
                catch { }
            }
        }
    }

    private static BridgeResponse ErrorResponse(int statusCode, string code, string message)
    {
        var response = BridgeResponse.Json(statusCode, new { ok = false, code, message });
        return response.WithHeaders(new Dictionary<string, string>
        {
            ["Cache-Control"] = "no-store",
            ["X-Content-Type-Options"] = "nosniff",
        });
    }

    private static async Task<BridgeRequest> ReadRequestAsync(NetworkStream stream, CancellationToken cancellationToken)
    {
        var bytes = new List<byte>(512);
        var buffer = new byte[1];
        while (bytes.Count < MaxHeaderBytes)
        {
            var read = await stream.ReadAsync(buffer, cancellationToken).ConfigureAwait(false);
            if (read == 0)
            {
                break;
            }

            bytes.Add(buffer[0]);
            var count = bytes.Count;
            if (count >= 4
                && bytes[count - 4] == '\r'
                && bytes[count - 3] == '\n'
                && bytes[count - 2] == '\r'
                && bytes[count - 1] == '\n')
            {
                break;
            }
        }

        if (bytes.Count == 0 || bytes.Count >= MaxHeaderBytes)
        {
            throw new InvalidDataException("Request headers are empty or too large.");
        }

        var text = Encoding.ASCII.GetString(bytes.ToArray());
        var lines = text.Split("\r\n", StringSplitOptions.None);
        var requestLine = lines[0].Split(' ', StringSplitOptions.RemoveEmptyEntries);
        if (requestLine.Length != 3 || !requestLine[2].StartsWith("HTTP/1.", StringComparison.Ordinal))
        {
            throw new InvalidDataException("Invalid request line.");
        }

        var target = requestLine[1];
        var queryIndex = target.IndexOf('?');
        var path = queryIndex >= 0 ? target[..queryIndex] : target;
        if (!path.StartsWith('/') || path.Contains('\0'))
        {
            throw new InvalidDataException("Invalid request target.");
        }

        var headers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var line in lines.Skip(1))
        {
            if (line.Length == 0)
            {
                break;
            }

            var separator = line.IndexOf(':');
            if (separator <= 0)
            {
                throw new InvalidDataException("Invalid request header.");
            }

            headers[line[..separator].Trim()] = line[(separator + 1)..].Trim();
        }

        if (headers.TryGetValue("Transfer-Encoding", out var transferEncoding)
            && !string.Equals(transferEncoding, "identity", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Request bodies are not supported.");
        }
        if (headers.TryGetValue("Content-Length", out var contentLength)
            && (!long.TryParse(contentLength, out var length) || length != 0))
        {
            throw new InvalidDataException("Request bodies are not supported.");
        }

        return new BridgeRequest(requestLine[0], path, headers);
    }

    private static async Task WriteResponseAsync(NetworkStream stream, BridgeResponse response, CancellationToken cancellationToken)
    {
        var builder = new StringBuilder()
            .Append("HTTP/1.1 ").Append(response.StatusCode).Append(' ').Append(ReasonPhrase(response.StatusCode)).Append("\r\n")
            .Append("Connection: close\r\n")
            .Append("Content-Length: ").Append(response.Body.Length).Append("\r\n");
        if (!string.IsNullOrWhiteSpace(response.ContentType))
        {
            builder.Append("Content-Type: ").Append(response.ContentType).Append("\r\n");
        }
        foreach (var (name, value) in response.Headers)
        {
            builder.Append(name).Append(": ").Append(value).Append("\r\n");
        }
        builder.Append("\r\n");

        await stream.WriteAsync(Encoding.ASCII.GetBytes(builder.ToString()), cancellationToken).ConfigureAwait(false);
        if (response.Body.Length > 0)
        {
            await stream.WriteAsync(response.Body, cancellationToken).ConfigureAwait(false);
        }
        await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
    }

    private static string ReasonPhrase(int statusCode) => statusCode switch
    {
        200 => "OK",
        204 => "No Content",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        409 => "Conflict",
        413 => "Content Too Large",
        500 => "Internal Server Error",
        503 => "Service Unavailable",
        _ => "Response",
    };

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _lifetime.Cancel();
        _listener.Stop();
        try { _acceptLoop?.Wait(TimeSpan.FromSeconds(2)); } catch (AggregateException) { }
        _lifetime.Dispose();
    }
}
