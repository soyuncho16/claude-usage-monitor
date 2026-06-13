using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using ClaudeUsage.Core;

namespace ClaudeUsage.Tray;

public static class IconRenderer
{
    private static Color ToColor(UsageColor c) => c switch
    {
        UsageColor.Green => Color.FromArgb(0x57, 0xe3, 0x89),
        UsageColor.Yellow => Color.FromArgb(0xf8, 0xe4, 0x5c),
        UsageColor.Red => Color.FromArgb(0xff, 0x6b, 0x6b),
        _ => Color.FromArgb(0x9a, 0x99, 0x96),
    };

    /// <summary>퍼센트 숫자를 색 원 위에 그려 트레이 아이콘 생성. 호출자가 Icon과 HICON을 해제.</summary>
    public static Icon Render(string text, UsageColor color)
    {
        const int size = 32;  // 고해상도; Windows가 트레이에 맞게 다운스케일
        using var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.Clear(Color.Transparent);
            using var bg = new SolidBrush(ToColor(color));
            g.FillEllipse(bg, 0, 0, size - 1, size - 1);

            var fontSize = text.Length >= 3 ? 11f : 15f;  // "100"은 작게, "47"/"!"는 크게
            using var font = new Font("Segoe UI", fontSize, FontStyle.Bold, GraphicsUnit.Pixel);
            using var fg = new SolidBrush(Color.Black);
            using var fmt = new StringFormat
            {
                Alignment = StringAlignment.Center,
                LineAlignment = StringAlignment.Center,
            };
            g.DrawString(text, font, fg, new RectangleF(0, 0, size, size), fmt);
        }
        return Icon.FromHandle(bmp.GetHicon());  // HICON은 TrayContext가 DestroyIcon으로 해제
    }
}
