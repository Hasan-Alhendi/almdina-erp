using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

namespace Almdina.ScannerBridge.Infrastructure;

internal sealed record NormalizedScannerImage(
    byte[] JpegBytes,
    string SourceFormat,
    int SourceBytes,
    int SourceWidth,
    int SourceHeight,
    int OutputWidth,
    int OutputHeight,
    int JpegQuality
)
{
    public bool WasResized => SourceWidth != OutputWidth || SourceHeight != OutputHeight;
}

internal sealed class ScannerImageNormalizer
{
    internal const int InitialJpegQuality = 88;

    private const long MaxWorkingPixels = 24_000_000;
    private const int MinimumLongEdgePixels = 900;
    private const int MaxResizeAttempts = 6;
    private static readonly int[] JpegQualities = [InitialJpegQuality, 80, 72, 64, 56, 48, 40, 32];
    private static readonly ImageCodecInfo JpegCodec = ImageCodecInfo.GetImageEncoders()
        .Single(codec => codec.FormatID == ImageFormat.Jpeg.Guid);

    public NormalizedScannerImage Normalize(byte[] sourceBytes, int maxOutputBytes)
    {
        ArgumentNullException.ThrowIfNull(sourceBytes);
        if (sourceBytes.Length == 0)
        {
            throw new InvalidDataException("Scanner returned an empty image.");
        }
        if (maxOutputBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maxOutputBytes));
        }

        try
        {
            using var sourceStream = new MemoryStream(sourceBytes, writable: false);
            using var sourceImage = Image.FromStream(
                sourceStream,
                useEmbeddedColorManagement: true,
                validateImageData: true
            );
            if (sourceImage.Width <= 0 || sourceImage.Height <= 0)
            {
                throw new InvalidDataException("Scanner returned an image with invalid dimensions.");
            }

            var sourceFormat = FormatName(sourceImage.RawFormat);
            var (width, height) = LimitWorkingDimensions(sourceImage.Width, sourceImage.Height);
            NormalizedScannerImage? smallest = null;

            for (var resizeAttempt = 0; resizeAttempt < MaxResizeAttempts; resizeAttempt++)
            {
                using var rendered = RenderRgb(sourceImage, width, height);
                NormalizedScannerImage? smallestAtThisSize = null;
                foreach (var quality in JpegQualities)
                {
                    var jpegBytes = EncodeJpeg(rendered, quality);
                    var candidate = new NormalizedScannerImage(
                        jpegBytes,
                        sourceFormat,
                        sourceBytes.Length,
                        sourceImage.Width,
                        sourceImage.Height,
                        width,
                        height,
                        quality
                    );
                    if (smallest is null || candidate.JpegBytes.Length < smallest.JpegBytes.Length)
                    {
                        smallest = candidate;
                    }
                    if (smallestAtThisSize is null || candidate.JpegBytes.Length < smallestAtThisSize.JpegBytes.Length)
                    {
                        smallestAtThisSize = candidate;
                    }
                    if (candidate.JpegBytes.Length <= maxOutputBytes)
                    {
                        return candidate;
                    }
                }

                var longEdge = Math.Max(width, height);
                if (longEdge <= MinimumLongEdgePixels || smallestAtThisSize is null)
                {
                    break;
                }

                var sizeRatio = Math.Sqrt((double)maxOutputBytes / smallestAtThisSize.JpegBytes.Length) * 0.92;
                var resizeRatio = Math.Clamp(sizeRatio, 0.55, 0.85);
                var nextWidth = Math.Max(1, (int)Math.Round(width * resizeRatio));
                var nextHeight = Math.Max(1, (int)Math.Round(height * resizeRatio));
                if (nextWidth == width && nextHeight == height)
                {
                    break;
                }
                width = nextWidth;
                height = nextHeight;
            }

            return smallest ?? throw new InvalidDataException("Scanner image could not be encoded as JPEG.");
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception error) when (error is ArgumentException or ExternalException or OutOfMemoryException)
        {
            throw new InvalidDataException("Scanner returned an unsupported or corrupt image.", error);
        }
    }

    private static (int Width, int Height) LimitWorkingDimensions(int width, int height)
    {
        var pixels = (long)width * height;
        if (pixels <= MaxWorkingPixels)
        {
            return (width, height);
        }

        var ratio = Math.Sqrt((double)MaxWorkingPixels / pixels);
        return (
            Math.Max(1, (int)Math.Round(width * ratio)),
            Math.Max(1, (int)Math.Round(height * ratio))
        );
    }

    private static Bitmap RenderRgb(Image source, int width, int height)
    {
        var bitmap = new Bitmap(width, height, PixelFormat.Format24bppRgb);
        CopyResolution(source, bitmap);
        using var graphics = Graphics.FromImage(bitmap);
        graphics.Clear(Color.White);
        graphics.CompositingQuality = CompositingQuality.HighQuality;
        graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
        graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
        graphics.SmoothingMode = SmoothingMode.HighQuality;
        graphics.DrawImage(
            source,
            new Rectangle(0, 0, width, height),
            0,
            0,
            source.Width,
            source.Height,
            GraphicsUnit.Pixel
        );
        return bitmap;
    }

    private static void CopyResolution(Image source, Bitmap destination)
    {
        try
        {
            var horizontal = source.HorizontalResolution;
            var vertical = source.VerticalResolution;
            if (float.IsFinite(horizontal) && float.IsFinite(vertical) && horizontal > 0 && vertical > 0)
            {
                destination.SetResolution(horizontal, vertical);
            }
        }
        catch (ArgumentException)
        {
            // Invalid scanner DPI metadata must not block decoding the pixels.
        }
    }

    private static byte[] EncodeJpeg(Image image, int quality)
    {
        using var stream = new MemoryStream();
        using var parameters = new EncoderParameters(1);
        parameters.Param[0] = new EncoderParameter(System.Drawing.Imaging.Encoder.Quality, (long)quality);
        image.Save(stream, JpegCodec, parameters);
        return stream.ToArray();
    }

    private static string FormatName(ImageFormat format)
    {
        if (format.Guid == ImageFormat.Bmp.Guid) return "BMP";
        if (format.Guid == ImageFormat.Gif.Guid) return "GIF";
        if (format.Guid == ImageFormat.Jpeg.Guid) return "JPEG";
        if (format.Guid == ImageFormat.Png.Guid) return "PNG";
        if (format.Guid == ImageFormat.Tiff.Guid) return "TIFF";
        return format.Guid.ToString("D");
    }
}
