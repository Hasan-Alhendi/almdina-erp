Add-Type -AssemblyName System.Drawing
$alnsRoot = (Get-Location).Path
foreach ($alnsCase in @('108', '154', '263', '298')) {
    $alnsDrawingPath = Join-Path $alnsRoot "docs/evidence/pattern-search/report/drawing-$alnsCase.json"
    $alnsDrawing = Get-Content -LiteralPath $alnsDrawingPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $alnsBitmap = [System.Drawing.Bitmap]::new([int]$alnsDrawing.width, [int]$alnsDrawing.height)
    $alnsGraphics = [System.Drawing.Graphics]::FromImage($alnsBitmap)
    $alnsGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $alnsGraphics.Clear([System.Drawing.Color]::FromArgb(245,247,250))
    $alnsFont = [System.Drawing.Font]::new('Arial',11,[System.Drawing.FontStyle]::Regular,[System.Drawing.GraphicsUnit]::Pixel)
    $alnsTitleFont = [System.Drawing.Font]::new('Arial',18,[System.Drawing.FontStyle]::Regular,[System.Drawing.GraphicsUnit]::Pixel)
    $alnsTextBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(25,51,74))
    $alnsLinePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(53,80,100),[single]0.45)
    $alnsGraphics.DrawString("Order ${alnsCase}: actual material outlines - Kerf 5 mm",$alnsTitleFont,$alnsTextBrush,[single]20,[single]12)
    $alnsGraphics.DrawString('Measured cutter-center network; these images are not CNC sequence certification.',$alnsFont,$alnsTextBrush,[single]20,[single]38)
    for ($alnsPanelIndex=0; $alnsPanelIndex -lt $alnsDrawing.panels.Count; $alnsPanelIndex++) {
        $alnsPanel = $alnsDrawing.panels[$alnsPanelIndex]
        $alnsPanelX = 20+$alnsPanelIndex*325
        $alnsGraphics.DrawString([string]$alnsPanel.label,$alnsFont,$alnsTextBrush,[single]$alnsPanelX,[single]62)
        $alnsMetrics = $alnsPanel.metrics
        $alnsMetricText = '{0} boards | remnant {1:F6} m2' -f $alnsMetrics.boards,$alnsMetrics.reusable_m2
        $alnsGraphics.DrawString($alnsMetricText,$alnsFont,$alnsTextBrush,[single]$alnsPanelX,[single]80)
        $alnsNetworkText = 'Cutter {0:F4} m | {1} segments' -f ($alnsMetrics.cutter_profile[0]/1000),$alnsMetrics.cutter_profile[1]
        $alnsGraphics.DrawString($alnsNetworkText,$alnsFont,$alnsTextBrush,[single]$alnsPanelX,[single]98)
        $alnsBoardNo = 0
        foreach ($alnsSheet in $alnsPanel.sheets) {
            $alnsBoardNo++
            $alnsGraphics.FillRectangle([System.Drawing.Brushes]::White,[single]$alnsSheet.x,[single]$alnsSheet.y,[single]$alnsSheet.w,[single]$alnsSheet.h)
            $alnsGraphics.DrawRectangle($alnsLinePen,[single]$alnsSheet.x,[single]$alnsSheet.y,[single]$alnsSheet.w,[single]$alnsSheet.h)
            foreach ($alnsPolygon in $alnsSheet.polygons) {
                $alnsPoints = [System.Drawing.PointF[]]@($alnsPolygon.points | ForEach-Object { [System.Drawing.PointF]::new([single]($alnsSheet.x+$_[0]),[single]($alnsSheet.y+$_[1])) })
                $alnsFill = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml($alnsPolygon.color))
                $alnsGraphics.FillPolygon($alnsFill,$alnsPoints)
                $alnsGraphics.DrawPolygon($alnsLinePen,$alnsPoints)
                $alnsFill.Dispose()
            }
            $alnsBoardText = 'Board {0}: {1} pieces' -f $alnsBoardNo,$alnsSheet.polygons.Count
            $alnsGraphics.DrawString($alnsBoardText,$alnsFont,$alnsTextBrush,[single]$alnsSheet.x,[single]($alnsSheet.y+$alnsSheet.h+6))
        }
    }
    $alnsPngPath = Join-Path $alnsRoot "docs/evidence/pattern-search/report/comparison-$alnsCase.png"
    $alnsBitmap.Save($alnsPngPath,[System.Drawing.Imaging.ImageFormat]::Png)
    $alnsGraphics.Dispose(); $alnsBitmap.Dispose(); $alnsFont.Dispose(); $alnsTitleFont.Dispose(); $alnsTextBrush.Dispose(); $alnsLinePen.Dispose()
    Write-Output $alnsPngPath
}
