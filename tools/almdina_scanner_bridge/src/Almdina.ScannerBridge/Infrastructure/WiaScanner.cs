using Almdina.ScannerBridge.Core;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace Almdina.ScannerBridge.Infrastructure;

internal sealed class WiaScanner : IScanner, IDisposable
{
    private const string WiaCommonDialogProgId = "WIA.CommonDialog";
    private const string JpegFormatId = "{B96B3CAE-0728-11D3-9D7B-0000F81EF32E}";

    private readonly Control _uiDispatcher;
    private readonly FileLogger _logger;
    private readonly ScannerImageNormalizer _imageNormalizer = new();
    private int _busy;
    private bool _disposed;

    public WiaScanner(Control uiDispatcher, FileLogger logger)
    {
        _uiDispatcher = uiDispatcher;
        _logger = logger;
    }

    public Task<ScanOutcome> AcquireJpegAsync(CancellationToken cancellationToken)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        if (Interlocked.CompareExchange(ref _busy, 1, 0) != 0)
        {
            throw new ScannerBusyException();
        }

        var completion = new TaskCompletionSource<ScanOutcome>(TaskCreationOptions.RunContinuationsAsynchronously);
        void Acquire()
        {
            try
            {
                cancellationToken.ThrowIfCancellationRequested();
                completion.TrySetResult(AcquireOnUiThread());
            }
            catch (OperationCanceledException)
            {
                completion.TrySetCanceled(cancellationToken);
            }
            catch (Exception error)
            {
                completion.TrySetException(error);
            }
            finally
            {
                Interlocked.Exchange(ref _busy, 0);
            }
        }

        try
        {
            if (_uiDispatcher.InvokeRequired)
            {
                _uiDispatcher.BeginInvoke((Action)Acquire);
            }
            else
            {
                Acquire();
            }
        }
        catch
        {
            Interlocked.Exchange(ref _busy, 0);
            throw;
        }

        return completion.Task;
    }

    private ScanOutcome AcquireOnUiThread()
    {
        object? dialog = null;
        object? image = null;
        string? temporaryPath = null;
        try
        {
            var dialogType = Type.GetTypeFromProgID(WiaCommonDialogProgId, throwOnError: false);
            if (dialogType is null)
            {
                throw new ScannerUnavailableException("Windows Image Acquisition is unavailable.");
            }

            dialog = Activator.CreateInstance(dialogType)
                ?? throw new ScannerUnavailableException("Windows could not create the scanner dialog.");
            dynamic commonDialog = dialog;

            // Scanner device, unspecified intent/bias, JPEG output. The final
            // false makes user cancellation return null instead of an error.
            image = commonDialog.ShowAcquireImage(1, 0, 0, JpegFormatId, true, true, false);
            if (image is null)
            {
                return ScanOutcome.Cancel();
            }

            temporaryPath = Path.Combine(Path.GetTempPath(), $"almadina-scan-{Guid.NewGuid():N}.wia");
            dynamic acquiredImage = image;
            acquiredImage.SaveFile(temporaryPath);
            var bytes = File.ReadAllBytes(temporaryPath);
            var normalized = _imageNormalizer.Normalize(bytes, BridgeOptions.MaxImageBytes);
            _logger.Info(
                $"Scanner returned {normalized.SourceBytes} bytes "
                + $"({normalized.SourceFormat}, {normalized.SourceWidth}x{normalized.SourceHeight}); "
                + $"normalized to JPEG {normalized.JpegBytes.Length} bytes "
                + $"({normalized.OutputWidth}x{normalized.OutputHeight}, quality {normalized.JpegQuality})."
            );
            return ScanOutcome.Success(normalized.JpegBytes);
        }
        catch (ScannerUnavailableException)
        {
            throw;
        }
        catch (COMException error)
        {
            _logger.Error("WIA scanner acquisition failed.", error);
            throw new ScannerAcquisitionException("WIA scanner acquisition failed.", error);
        }
        catch (Exception error)
        {
            _logger.Error("Scanner image acquisition or normalization failed.", error);
            throw new ScannerAcquisitionException("Scanner acquisition failed.", error);
        }
        finally
        {
            if (temporaryPath is not null)
            {
                try { File.Delete(temporaryPath); }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException)
                {
                    _logger.Error("Could not delete temporary scanner image.", error);
                }
            }
            ReleaseComObject(image);
            ReleaseComObject(dialog);
        }
    }

    private static void ReleaseComObject(object? value)
    {
        if (value is not null && Marshal.IsComObject(value))
        {
            try { Marshal.FinalReleaseComObject(value); }
            catch (Exception error) when (error is InvalidComObjectException or COMException) { }
        }
    }

    public void Dispose()
    {
        _disposed = true;
    }
}
