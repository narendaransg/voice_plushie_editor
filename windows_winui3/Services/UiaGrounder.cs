using System.Runtime.InteropServices;
using System.Windows.Automation;

namespace VoicePlushie.Services;

public static class UiaGrounder
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    public static List<OverlayTargetItem> DetectActiveWindowControls(int maxItems = 12)
    {
        var results = new List<OverlayTargetItem>();
        var hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero || hwnd == new WindowHandleHolder().Handle)
        {
            return results;
        }

        try
        {
            var root = AutomationElement.FromHandle(hwnd);
            if (root == null) return results;

            var condition = new OrCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Slider),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.TabItem),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.MenuItem),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Group),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ToolBar)
            );

            var found = root.FindAll(TreeScope.Descendants, condition);
            int idx = 1;
            foreach (AutomationElement el in found)
            {
                if (results.Count >= maxItems) break;
                try
                {
                    var rect = el.Current.BoundingRectangle;
                    if (rect.IsEmpty || double.IsInfinity(rect.Width) || double.IsInfinity(rect.Height))
                        continue;
                    int w = (int)Math.Round(rect.Width);
                    int h = (int)Math.Round(rect.Height);
                    if (w < 18 || h < 16 || w > 1800 || h > 1100) continue;

                    int x = (int)Math.Round(rect.Left);
                    int y = (int)Math.Round(rect.Top);
                    if (results.Any(existing => Math.Abs(existing.Left - x) < 12 && Math.Abs(existing.Top - y) < 12 && Math.Abs(existing.Width - w) < 12))
                        continue;

                    string role = MapControlRole(el.Current.ControlType, w, h);
                    string rawName = (el.Current.Name ?? string.Empty).Trim();
                    string label = string.IsNullOrWhiteSpace(rawName) ? $"{role} {idx}" : $"{role}:{rawName}";

                    results.Add(new OverlayTargetItem
                    {
                        Index = idx++,
                        Name = label.Length > 20 ? label[..20] : label,
                        Role = role,
                        Left = x,
                        Top = y,
                        Width = w,
                        Height = h
                    });
                }
                catch
                {
                    // Skip inaccessible element
                }
            }
        }
        catch
        {
            // Return empty list to use layout sectors
        }

        return results;
    }

    private static string MapControlRole(ControlType ct, int w, int h)
    {
        if (ct == ControlType.Slider) return "Slider";
        if (w >= h * 4.5 && h <= 36) return "Slider";
        if (ct == ControlType.Button || ct == ControlType.MenuItem || ct == ControlType.TabItem) return "Button";
        if (w >= 260 && h >= 80 && w > h * 2.2) return "Timeline";
        return "Panel";
    }

    private sealed class WindowHandleHolder
    {
        public IntPtr Handle => IntPtr.Zero;
    }
}
