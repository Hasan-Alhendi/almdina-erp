using Almdina.ScannerBridge.Infrastructure;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;

var tests = new (string Name, Action Run)[]
{
    ("BMP scanner output becomes a real JPEG", NormalizeBmpToJpeg),
    ("raw scanner output above 8 MB is normalized below the production limit", NormalizeIncidentSizedImage),
    ("large scanner output is compressed below the upload limit", CompressLargeImage),
    ("invalid scanner output fails explicitly", RejectInvalidImage),
};

var failures = new List<string>();
foreach (var (name, run) in tests)
{
    try
    {
        run();
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

static void NormalizeBmpToJpeg()
{
    var source = CreateBmp(640, 480, noisy: false);
    var result = new ScannerImageNormalizer().Normalize(source, 8 * 1024 * 1024);

    Equal("BMP", result.SourceFormat);
    Equal(source.Length, result.SourceBytes);
    Equal(640, result.SourceWidth);
    Equal(480, result.SourceHeight);
    Jpeg(result.JpegBytes);
    True(result.JpegBytes.Length < source.Length, "The normalized reference should be smaller than the raw BMP.");
}

static void NormalizeIncidentSizedImage()
{
    var source = CreateBmp(2400, 1700, noisy: true);
    const int productionLimit = 8 * 1024 * 1024;
    True(source.Length > productionLimit, "The regression fixture must reproduce a raw image above 8 MB.");

    var result = new ScannerImageNormalizer().Normalize(source, productionLimit);

    Jpeg(result.JpegBytes);
    True(result.JpegBytes.Length <= productionLimit,
        $"Expected at most {productionLimit} bytes, got {result.JpegBytes.Length}.");
}

static void CompressLargeImage()
{
    var source = CreateBmp(1600, 1200, noisy: true);
    const int testLimit = 350 * 1024;
    var result = new ScannerImageNormalizer().Normalize(source, testLimit);

    Jpeg(result.JpegBytes);
    True(result.JpegBytes.Length <= testLimit, $"Expected at most {testLimit} bytes, got {result.JpegBytes.Length}.");
    True(result.JpegQuality < ScannerImageNormalizer.InitialJpegQuality || result.WasResized,
        "An oversized, high-entropy scan must use adaptive compression or resizing.");
}

static void RejectInvalidImage()
{
    try
    {
        _ = new ScannerImageNormalizer().Normalize("not-an-image"u8.ToArray(), 8 * 1024 * 1024);
        throw new InvalidOperationException("Invalid scanner bytes were accepted.");
    }
    catch (InvalidDataException)
    {
    }
}

static byte[] CreateBmp(int width, int height, bool noisy)
{
    using var bitmap = new Bitmap(width, height, PixelFormat.Format24bppRgb);
    if (noisy)
    {
        var area = new Rectangle(0, 0, width, height);
        var data = bitmap.LockBits(area, ImageLockMode.WriteOnly, PixelFormat.Format24bppRgb);
        try
        {
            var pixels = new byte[Math.Abs(data.Stride) * height];
            new Random(20260827).NextBytes(pixels);
            Marshal.Copy(pixels, 0, data.Scan0, pixels.Length);
        }
        finally
        {
            bitmap.UnlockBits(data);
        }
    }
    else
    {
        using var graphics = Graphics.FromImage(bitmap);
        graphics.Clear(Color.White);
        using var pen = new Pen(Color.Navy, 12);
        graphics.DrawRectangle(pen, 35, 35, width - 70, height - 70);
        graphics.DrawLine(pen, 60, height - 80, width - 60, 80);
    }

    using var stream = new MemoryStream();
    bitmap.Save(stream, ImageFormat.Bmp);
    return stream.ToArray();
}

static void Jpeg(byte[] bytes)
{
    True(bytes.Length >= 3 && bytes[0] == 0xff && bytes[1] == 0xd8 && bytes[2] == 0xff,
        "Expected a JPEG signature.");
    using var stream = new MemoryStream(bytes, writable: false);
    using var decoded = Image.FromStream(stream, useEmbeddedColorManagement: true, validateImageData: true);
    Equal(ImageFormat.Jpeg.Guid, decoded.RawFormat.Guid);
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
    if (!value)
    {
        throw new InvalidOperationException(message);
    }
}
