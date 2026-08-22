namespace Almdina.ScannerBridge.Core;

public interface IScanner
{
    Task<ScanOutcome> AcquireJpegAsync(CancellationToken cancellationToken);
}

public sealed record ScanOutcome(bool Cancelled, byte[]? JpegBytes)
{
    public static ScanOutcome Cancel() => new(true, null);

    public static ScanOutcome Success(byte[] jpegBytes) => new(false, jpegBytes);
}

public sealed class ScannerBusyException : Exception
{
    public ScannerBusyException() : base("A scan is already in progress.") { }
}

public sealed class ScannerUnavailableException : Exception
{
    public ScannerUnavailableException(string message, Exception? innerException = null) : base(message, innerException) { }
}

public sealed class ScannerAcquisitionException : Exception
{
    public ScannerAcquisitionException(string message, Exception? innerException = null) : base(message, innerException) { }
}
