using System.Text.RegularExpressions;

namespace VoicePlushie.Services;

public sealed class OverlayTargetItem
{
    public int Index { get; set; }
    public string Name { get; set; } = string.Empty;
    public string Role { get; set; } = "Panel";
    public int Left { get; set; }
    public int Top { get; set; }
    public int Width { get; set; }
    public int Height { get; set; }
    public int CenterX => Left + Width / 2;
    public int CenterY => Top + Height / 2;
}

public sealed class CommandRouter
{
    private static readonly Dictionary<string, int> WordNumbers = new(StringComparer.OrdinalIgnoreCase)
    {
        ["one"] = 1, ["two"] = 2, ["three"] = 3, ["four"] = 4, ["five"] = 5,
        ["six"] = 6, ["seven"] = 7, ["eight"] = 8, ["nine"] = 9, ["ten"] = 10,
        ["eleven"] = 11, ["twelve"] = 12, ["thirteen"] = 13, ["fourteen"] = 14, ["fifteen"] = 15,
        ["sixteen"] = 16, ["seventeen"] = 17, ["eighteen"] = 18, ["nineteen"] = 19, ["twenty"] = 20
    };

    private readonly Dictionary<string, EditorProfile> _profiles;
    private readonly Stack<(string Level, List<OverlayTargetItem> Items)> _history = new();
    private Win32InputService.RECT _lastWindowRect;

    public string ActiveEditorKey { get; set; } = "clipchamp";
    public string CurrentLevel { get; private set; } = "sectors";
    public List<OverlayTargetItem> ActiveTargets { get; private set; } = new();
    public bool IsDragging { get; private set; }

    public CommandRouter(Dictionary<string, EditorProfile> profiles)
    {
        _profiles = profiles;
        _lastWindowRect = Win32InputService.GetActiveWindowRect();
    }

    public int ShowSectors()
    {
        _history.Clear();
        IsDragging = false;
        Win32InputService.MouseUp("left");

        var win = Win32InputService.GetActiveWindowRect();
        _lastWindowRect = win;
        int w = win.Width;
        int h = win.Height;
        int x = win.Left;
        int y = win.Top;

        int headerH = Math.Clamp((int)(h * 0.055), 36, 52);
        int leftW = Math.Clamp((int)(w * 0.045), 44, 62);
        int rightW = Math.Clamp((int)(w * 0.052), 48, 72);
        int timelineH = Math.Clamp((int)(h * 0.34), 140, Math.Max(150, h - headerH - 120));
        int mainTop = y + headerH + 2;
        int mainH = Math.Max(120, h - headerH - timelineH - 6);
        int drawerW = Math.Clamp((int)(w * 0.20), 140, Math.Max(160, w - leftW - rightW - 220));
        int previewX = x + leftW + drawerW + 4;
        int previewW = Math.Max(180, (x + w - rightW - 4) - previewX);

        var uiaTargets = UiaGrounder.DetectActiveWindowControls(12);
        if (uiaTargets.Count >= 3)
        {
            ActiveTargets = uiaTargets;
            CurrentLevel = "groups";
            return ActiveTargets.Count;
        }

        ActiveTargets = new List<OverlayTargetItem>
        {
            new() { Index = 1, Name = "Header", Role = "Panel", Left = x + leftW, Top = y + 2, Width = Math.Max(120, w - leftW - rightW), Height = headerH },
            new() { Index = 2, Name = "Left Rail", Role = "Panel", Left = x + 2, Top = mainTop, Width = leftW, Height = mainH + timelineH },
            new() { Index = 3, Name = "Drawer", Role = "Panel", Left = x + leftW + 2, Top = mainTop, Width = drawerW, Height = mainH },
            new() { Index = 4, Name = "Preview", Role = "Zoomable", Left = previewX, Top = mainTop, Width = previewW, Height = mainH },
            new() { Index = 5, Name = "Right Rail", Role = "Panel", Left = x + w - rightW - 2, Top = mainTop, Width = rightW, Height = mainH },
            new() { Index = 6, Name = "Timeline", Role = "Timeline", Left = x + leftW + 2, Top = mainTop + mainH + 2, Width = Math.Max(200, w - leftW - rightW - 4), Height = timelineH }
        };
        CurrentLevel = "sectors";
        return ActiveTargets.Count;
    }

    public int DrillInto(OverlayTargetItem target)
    {
        _history.Push((CurrentLevel, new List<OverlayTargetItem>(ActiveTargets)));

        string nextLevel = CurrentLevel switch
        {
            "sectors" => "groups",
            "groups" => "spots",
            _ => "spots"
        };

        int cols = target.Width >= target.Height * 2.2 ? 3 : 2;
        int rows = target.Height >= target.Width * 2.2 ? 3 : 2;
        if (cols == 3 && rows == 3) rows = 1;
        if (rows == 3 && cols == 3) cols = 1;

        int cw = Math.Max(16, target.Width / cols);
        int ch = Math.Max(16, target.Height / rows);

        var items = new List<OverlayTargetItem>();
        int idx = 1;
        for (int r = 0; r < rows; r++)
        {
            for (int c = 0; c < cols; c++)
            {
                int ix = target.Left + c * cw;
                int iy = target.Top + r * ch;
                int iw = (c == cols - 1) ? Math.Max(16, target.Left + target.Width - ix) : cw;
                int ih = (r == rows - 1) ? Math.Max(16, target.Top + target.Height - iy) : ch;
                string label = nextLevel == "groups" ? $"Group {idx}" : $"Spot {idx}";
                string role = nextLevel == "groups" ? "Button" : "Zoomable";
                items.Add(new OverlayTargetItem
                {
                    Index = idx++,
                    Name = label,
                    Role = role,
                    Left = ix,
                    Top = iy,
                    Width = iw,
                    Height = ih
                });
            }
        }

        ActiveTargets = items;
        CurrentLevel = nextLevel;
        return ActiveTargets.Count;
    }

    public int ShowDropTargets()
    {
        _history.Push((CurrentLevel, new List<OverlayTargetItem>(ActiveTargets)));
        var win = _lastWindowRect.Width > 120 ? _lastWindowRect : Win32InputService.GetActiveWindowRect();
        var timeline = ActiveTargets.FirstOrDefault(t => t.Name.Contains("Timeline", StringComparison.OrdinalIgnoreCase))
            ?? new OverlayTargetItem
            {
                Left = win.Left + (int)(win.Width * 0.18),
                Top = win.Top + (int)(win.Height * 0.72),
                Width = Math.Max(220, (int)(win.Width * 0.74)),
                Height = Math.Max(120, (int)(win.Height * 0.24))
            };

        int slotW = Math.Max(70, timeline.Width / 3);
        int slotH = Math.Max(34, timeline.Height / 3);
        int trackY = timeline.Top + (int)(timeline.Height * 0.45);

        ActiveTargets = new List<OverlayTargetItem>
        {
            new() { Index = 1, Name = "Timeline Start", Role = "DropZone", Left = timeline.Left + 8, Top = trackY, Width = slotW, Height = slotH },
            new() { Index = 2, Name = "Timeline Mid", Role = "DropZone", Left = timeline.Left + slotW, Top = trackY, Width = slotW, Height = slotH },
            new() { Index = 3, Name = "Timeline End", Role = "DropZone", Left = timeline.Left + 2 * slotW, Top = trackY, Width = slotW, Height = slotH },
            new() { Index = 4, Name = "Top Track", Role = "DropZone", Left = timeline.Left + timeline.Width / 4, Top = timeline.Top + (int)(timeline.Height * 0.16), Width = Math.Max(90, timeline.Width / 2), Height = Math.Max(28, timeline.Height / 4) }
        };
        CurrentLevel = "drop_targets";
        return ActiveTargets.Count;
    }

    public string? GoUp()
    {
        if (_history.Count == 0)
        {
            ClearOverlay();
            return null;
        }
        var (prevLevel, prevItems) = _history.Pop();
        CurrentLevel = prevLevel;
        ActiveTargets = prevItems;
        return CurrentLevel;
    }

    public void ClearOverlay()
    {
        _history.Clear();
        ActiveTargets = new List<OverlayTargetItem>();
        CurrentLevel = "sectors";
    }

    public void ReleaseAll()
    {
        if (IsDragging)
        {
            Win32InputService.MouseUp("left");
            IsDragging = false;
        }
        ClearOverlay();
    }

    private static int? ExtractNumber(string text)
    {
        var m = Regex.Match(text, @"\b(\d{1,2})\b");
        if (m.Success && int.TryParse(m.Groups[1].Value, out int n))
        {
            return n;
        }
        foreach (var kv in WordNumbers.OrderByDescending(k => k.Key.Length))
        {
            if (Regex.IsMatch(text, $@"\b{Regex.Escape(kv.Key)}\b", RegexOptions.IgnoreCase))
            {
                return kv.Value;
            }
        }
        return null;
    }

    public string HandleUtterance(string utterance, out bool overlayChanged)
    {
        overlayChanged = false;
        var text = Regex.Replace(utterance.ToLowerInvariant().Trim(), @"\s+", " ");
        if (string.IsNullOrWhiteSpace(text))
        {
            return "Ready.";
        }

        int step = text.Contains("tiny") || text.Contains("pixel") ? 14
            : text.Contains("far") || text.Contains("fast") ? 140
            : 45;

        if (text is "stop" or "halt" or "freeze" or "stop moving")
        {
            return "Stopped.";
        }

        if (text.Contains("hide") || text.Contains("close labels") || text.Contains("clear labels") || text == "cancel")
        {
            ReleaseAll();
            overlayChanged = true;
            return "Overlay hidden and drag released.";
        }

        if (text is "go up" or "level up" or "back" or "go back" or "previous level")
        {
            var prev = GoUp();
            overlayChanged = true;
            return prev != null ? $"Moved up to '{prev}'." : "Exited overlay.";
        }

        if (text.Contains("show sectors") || text.Contains("show labels") || text == "sectors")
        {
            int count = ShowSectors();
            overlayChanged = true;
            return $"{count} sectors — say a number to hover/drill, 'drag', 'go up', or 'hide'.";
        }

        if (text.Contains("drop") || text.Contains("paste") || text.Contains("place") || text.Contains("release"))
        {
            Win32InputService.MouseUp("left");
            IsDragging = false;
            ClearOverlay();
            overlayChanged = true;
            return "Placed and released drag.";
        }

        if ((text.Contains("drag") || text.Contains("grab")) && !text.Contains("drop"))
        {
            int? num = ExtractNumber(text);
            var target = num != null ? ActiveTargets.FirstOrDefault(t => t.Index == num.Value) : null;
            if (target != null)
            {
                Win32InputService.MoveTo(target.CenterX, target.CenterY);
                Thread.Sleep(45);
            }
            Win32InputService.MouseDown("left");
            IsDragging = true;
            int destCount = ShowDropTargets();
            overlayChanged = true;
            return $"Holding item ({destCount} drop spots) — pick a spot number, 'hover left/right', then 'drop'.";
        }

        if (ActiveTargets.Count > 0)
        {
            int? num = ExtractNumber(text);
            if (num != null)
            {
                var item = ActiveTargets.FirstOrDefault(t => t.Index == num.Value);
                if (item != null)
                {
                    Win32InputService.MoveTo(item.CenterX, item.CenterY);
                    if (IsDragging || CurrentLevel == "drop_targets")
                    {
                        return $"Moved over '{item.Name}' — fine-tune with 'hover left/right' or say 'drop'.";
                    }
                    if (text.Contains("double click"))
                    {
                        Win32InputService.DoubleClick();
                        ClearOverlay();
                        overlayChanged = true;
                        return $"Double-clicked {item.Name}.";
                    }
                    if (text.Contains("right click"))
                    {
                        Win32InputService.Click("right");
                        ClearOverlay();
                        overlayChanged = true;
                        return $"Right-clicked {item.Name}.";
                    }
                    if (text.Contains("click"))
                    {
                        Win32InputService.Click("left");
                        ClearOverlay();
                        overlayChanged = true;
                        return $"Clicked {item.Name}.";
                    }

                    int subCount = DrillInto(item);
                    overlayChanged = true;
                    return $"Hovering #{item.Index} {item.Name} [{item.Role}] -> '{CurrentLevel}' ({subCount}) — pick a number, 'drag', 'click', or 'go up'.";
                }
            }
        }

        if (text.Contains("hover left") || text.Contains("nudge left") || text.Contains("move left") || text.Contains("go left"))
        {
            Win32InputService.MoveRelative(-step, 0);
            return IsDragging ? $"Moved left ({step}px) — say 'drop' to place." : $"Hover left ({step}px).";
        }
        if (text.Contains("hover right") || text.Contains("nudge right") || text.Contains("move right") || text.Contains("go right"))
        {
            Win32InputService.MoveRelative(step, 0);
            return IsDragging ? $"Moved right ({step}px) — say 'drop' to place." : $"Hover right ({step}px).";
        }
        if (text.Contains("hover up") || text.Contains("nudge up") || text.Contains("move up") || text.Contains("go up"))
        {
            Win32InputService.MoveRelative(0, -step);
            return IsDragging ? $"Moved up ({step}px) — say 'drop' to place." : $"Hover up ({step}px).";
        }
        if (text.Contains("hover down") || text.Contains("nudge down") || text.Contains("move down") || text.Contains("go down"))
        {
            Win32InputService.MoveRelative(0, step);
            return IsDragging ? $"Moved down ({step}px) — say 'drop' to place." : $"Hover down ({step}px).";
        }

        if (text == "click" || text == "left click")
        {
            Win32InputService.Click("left");
            return "Clicked.";
        }
        if (text == "double click")
        {
            Win32InputService.DoubleClick();
            return "Double-clicked.";
        }
        if (text == "right click")
        {
            Win32InputService.Click("right");
            return "Right-clicked.";
        }

        if (_profiles.TryGetValue(ActiveEditorKey, out var profile))
        {
            foreach (var kv in profile.Commands)
            {
                var cmd = kv.Value;
                if (!cmd.Supported || cmd.Keys.Count == 0) continue;
                bool matched = kv.Key.Replace("_", " ").Equals(text, StringComparison.OrdinalIgnoreCase)
                    || cmd.Aliases.Any(a => string.Equals(a, text, StringComparison.OrdinalIgnoreCase));
                if (matched)
                {
                    Win32InputService.SendKeyCombo(cmd.Keys);
                    return $"Executed '{kv.Key.Replace('_', ' ')}'.";
                }
            }
        }

        return $"Heard '{utterance}'";
    }
}
