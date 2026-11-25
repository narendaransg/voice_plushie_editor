using System.Runtime.InteropServices;

namespace VoicePlushie.Services;

public static class Win32InputService
{
    private const int GWL_EXSTYLE = -20;
    private const int WS_EX_TRANSPARENT = 0x00000020;
    private const int WS_EX_LAYERED = 0x00080000;
    private const int WS_EX_TOPMOST = 0x00000008;
    private const int WS_EX_TOOLWINDOW = 0x00000080;

    private const uint INPUT_MOUSE = 0;
    private const uint INPUT_KEYBOARD = 1;

    private const uint MOUSEEVENTF_MOVE = 0x0001;
    private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
    private const uint MOUSEEVENTF_LEFTUP = 0x0004;
    private const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
    private const uint MOUSEEVENTF_RIGHTUP = 0x0010;
    private const uint MOUSEEVENTF_WHEEL = 0x0800;
    private const uint MOUSEEVENTF_ABSOLUTE = 0x8000;

    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
        public int Width => Math.Max(1, Right - Left);
        public int Height => Math.Max(1, Bottom - Top);
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx;
        public int dy;
        public uint mouseData;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct INPUT
    {
        [FieldOffset(0)] public uint type;
        [FieldOffset(8)] public MOUSEINPUT mi;
        [FieldOffset(8)] public KEYBDINPUT ki;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [DllImport("user32.dll")]
    private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll")]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOACTIVATE = 0x0010;

    public static double GetDpiScale(IntPtr hwnd = default)
    {
        if (hwnd == IntPtr.Zero)
        {
            hwnd = GetForegroundWindow();
        }
        if (hwnd != IntPtr.Zero)
        {
            try
            {
                uint dpi = GetDpiForWindow(hwnd);
                if (dpi >= 96)
                {
                    return dpi / 96.0;
                }
            }
            catch
            {
                // Fallback below
            }
        }
        return 1.0;
    }

    public static void ConfigureClickThroughOverlay(IntPtr hwnd)
    {
        int exStyle = GetWindowLong(hwnd, GWL_EXSTYLE);
        exStyle |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW;
        SetWindowLong(hwnd, GWL_EXSTYLE, exStyle);
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    }

    public static (int Width, int Height) GetScreenSize()
    {
        int w = Math.Max(1, GetSystemMetrics(0));
        int h = Math.Max(1, GetSystemMetrics(1));
        return (w, h);
    }

    public static RECT GetActiveWindowRect()
    {
        var (sw, sh) = GetScreenSize();
        var hwnd = GetForegroundWindow();
        if (hwnd != IntPtr.Zero && GetWindowRect(hwnd, out var r) && r.Width > 120 && r.Height > 120)
        {
            return new RECT
            {
                Left = Math.Clamp(r.Left, 0, sw),
                Top = Math.Clamp(r.Top, 0, sh),
                Right = Math.Clamp(r.Right, 0, sw),
                Bottom = Math.Clamp(r.Bottom, 0, sh)
            };
        }
        return new RECT { Left = 0, Top = 0, Right = sw, Bottom = sh };
    }

    public static void MoveTo(int x, int y)
    {
        var (sw, sh) = GetScreenSize();
        int clampedX = Math.Clamp(x, 0, Math.Max(1, sw - 1));
        int clampedY = Math.Clamp(y, 0, Math.Max(1, sh - 1));
        int absX = (int)Math.Round(clampedX * 65535.0 / Math.Max(1, sw - 1));
        int absY = (int)Math.Round(clampedY * 65535.0 / Math.Max(1, sh - 1));
        var inp = new INPUT
        {
            type = INPUT_MOUSE,
            mi = new MOUSEINPUT
            {
                dx = absX,
                dy = absY,
                dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
            }
        };
        SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());
    }

    public static void MoveRelative(int dx, int dy)
    {
        var inp = new INPUT
        {
            type = INPUT_MOUSE,
            mi = new MOUSEINPUT
            {
                dx = dx,
                dy = dy,
                dwFlags = MOUSEEVENTF_MOVE
            }
        };
        SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());
    }

    public static void MouseDown(string button = "left")
    {
        uint flag = string.Equals(button, "right", StringComparison.OrdinalIgnoreCase)
            ? MOUSEEVENTF_RIGHTDOWN
            : MOUSEEVENTF_LEFTDOWN;
        var inp = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = flag } };
        SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());
    }

    public static void MouseUp(string button = "left")
    {
        uint flag = string.Equals(button, "right", StringComparison.OrdinalIgnoreCase)
            ? MOUSEEVENTF_RIGHTUP
            : MOUSEEVENTF_LEFTUP;
        var inp = new INPUT { type = INPUT_MOUSE, mi = new MOUSEINPUT { dwFlags = flag } };
        SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());
    }

    public static void Click(string button = "left")
    {
        MouseDown(button);
        Thread.Sleep(25);
        MouseUp(button);
    }

    public static void DoubleClick()
    {
        Click("left");
        Thread.Sleep(55);
        Click("left");
    }

    public static void Scroll(int delta)
    {
        var inp = new INPUT
        {
            type = INPUT_MOUSE,
            mi = new MOUSEINPUT
            {
                mouseData = unchecked((uint)delta),
                dwFlags = MOUSEEVENTF_WHEEL
            }
        };
        SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());
    }

    public static bool SendKeyCombo(IEnumerable<string> keys)
    {
        var vkList = new List<ushort>();
        foreach (var k in keys)
        {
            ushort? vk = MapKeyName(k);
            if (vk == null)
            {
                return false;
            }
            vkList.Add(vk.Value);
        }
        if (vkList.Count == 0)
        {
            return false;
        }

        var inputs = new List<INPUT>();
        foreach (var vk in vkList)
        {
            inputs.Add(new INPUT
            {
                type = INPUT_KEYBOARD,
                ki = new KEYBDINPUT { wVk = vk, dwFlags = IsExtendedKey(vk) ? KEYEVENTF_EXTENDEDKEY : 0 }
            });
        }
        for (int i = vkList.Count - 1; i >= 0; i--)
        {
            ushort vk = vkList[i];
            inputs.Add(new INPUT
            {
                type = INPUT_KEYBOARD,
                ki = new KEYBDINPUT { wVk = vk, dwFlags = KEYEVENTF_KEYUP | (IsExtendedKey(vk) ? KEYEVENTF_EXTENDEDKEY : 0) }
            });
        }

        SendInput((uint)inputs.Count, inputs.ToArray(), Marshal.SizeOf<INPUT>());
        return true;
    }

    private static bool IsExtendedKey(ushort vk) =>
        vk is 0x25 or 0x26 or 0x27 or 0x28 or 0x2E;

    private static ushort? MapKeyName(string name)
    {
        var n = name.Trim().ToLowerInvariant();
        return n switch
        {
            "ctrl" or "control" => 0x11,
            "shift" => 0x10,
            "alt" => 0x12,
            "space" => 0x20,
            "enter" or "return" => 0x0D,
            "esc" or "escape" => 0x1B,
            "tab" => 0x09,
            "delete" or "del" => 0x2E,
            "left" => 0x25,
            "up" => 0x26,
            "right" => 0x27,
            "down" => 0x28,
            "=" or "+" => 0xBB,
            "-" or "_" => 0xBD,
            _ when n.Length == 1 && char.IsLetterOrDigit(n[0]) => (ushort)char.ToUpperInvariant(n[0]),
            _ => null
        };
    }
}
