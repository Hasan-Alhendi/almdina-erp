namespace Almdina.ScannerBridge.Core;

public sealed class OriginPolicy
{
    private readonly HashSet<string> _allowedOrigins;

    public OriginPolicy(IEnumerable<string> allowedOrigins)
    {
        ArgumentNullException.ThrowIfNull(allowedOrigins);
        _allowedOrigins = new HashSet<string>(
            allowedOrigins.Select(NormalizeOrigin),
            StringComparer.OrdinalIgnoreCase
        );
    }

    public bool IsAllowed(string? origin)
    {
        if (string.IsNullOrWhiteSpace(origin))
        {
            return false;
        }

        try
        {
            return _allowedOrigins.Contains(NormalizeOrigin(origin));
        }
        catch (ArgumentException)
        {
            return false;
        }
    }

    private static string NormalizeOrigin(string value)
    {
        if (!Uri.TryCreate(value.Trim(), UriKind.Absolute, out var uri)
            || (uri.Scheme != Uri.UriSchemeHttp && uri.Scheme != Uri.UriSchemeHttps)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || uri.AbsolutePath != "/"
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment))
        {
            throw new ArgumentException("Origin must contain only an HTTP(S) scheme and authority.", nameof(value));
        }

        return uri.GetLeftPart(UriPartial.Authority);
    }
}
