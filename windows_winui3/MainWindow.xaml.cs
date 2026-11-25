using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using VoicePlushie.Services;

namespace VoicePlushie;

public partial class MainWindow : Window
{
    private readonly CommandRouter _router;
    private readonly Window _badgeOverlay;
    private readonly Canvas _badgeCanvas;
    private bool _cleanedUp;

    public MainWindow()
    {
        var repoRoot = FindRepoRoot();
        var profiles = ProfileLoader.LoadProfiles(Path.Combine(repoRoot, "config", "profiles"));
        _router = new CommandRouter(profiles);

        _badgeCanvas = new Canvas { Background = Brushes.Transparent };
        _badgeOverlay = new Window
        {
            WindowStyle = WindowStyle.None,
            AllowsTransparency = true,
            Background = Brushes.Transparent,
            Topmost = true,
            ShowInTaskbar = false,
            Content = _badgeCanvas
        };
        _badgeOverlay.Loaded += (_, _) =>
        {
            var hwnd = new WindowInteropHelper(_badgeOverlay).Handle;
            Win32InputService.ConfigureClickThroughOverlay(hwnd);
        };

        InitializeComponent();

        foreach (var k in profiles.Keys)
        {
            EditorCombo.Items.Add(k);
        }
        if (EditorCombo.Items.Count > 0)
        {
            EditorCombo.SelectedItem = profiles.ContainsKey("clipchamp") ? "clipchamp" : EditorCombo.Items[0];
        }

        Closed += (_, _) => CleanupAll();
    }

    private static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "config", "profiles")))
            {
                return dir.FullName;
            }
            dir = dir.Parent;
        }
        return Environment.CurrentDirectory;
    }

    private void RefreshOverlayVisuals()
    {
        if (_router.ActiveTargets.Count == 0)
        {
            if (_badgeOverlay.IsVisible)
            {
                _badgeOverlay.Hide();
            }
            _badgeCanvas.Children.Clear();
            return;
        }

        var (sw, sh) = Win32InputService.GetScreenSize();
        _badgeOverlay.Left = 0;
        _badgeOverlay.Top = 0;
        _badgeOverlay.Width = sw;
        _badgeOverlay.Height = sh;

        _badgeCanvas.Children.Clear();
        bool drawBox = _router.CurrentLevel == "sectors";

        foreach (var t in _router.ActiveTargets)
        {
            if (drawBox)
            {
                var rect = new System.Windows.Shapes.Rectangle
                {
                    Width = Math.Max(8, t.Width),
                    Height = Math.Max(8, t.Height),
                    Stroke = new SolidColorBrush(Color.FromRgb(80, 210, 255)),
                    StrokeThickness = 2,
                    Fill = Brushes.Transparent
                };
                Canvas.SetLeft(rect, t.Left);
                Canvas.SetTop(rect, t.Top);
                _badgeCanvas.Children.Add(rect);
            }

            Color badgeBg = _router.CurrentLevel switch
            {
                "drop_targets" => Color.FromRgb(42, 18, 52),
                "groups" => Color.FromRgb(32, 24, 10),
                "spots" => Color.FromRgb(18, 36, 28),
                _ => Color.FromRgb(16, 24, 38)
            };

            var badge = new Border
            {
                Background = new SolidColorBrush(badgeBg),
                BorderBrush = new SolidColorBrush(Color.FromRgb(80, 210, 255)),
                BorderThickness = new Thickness(1),
                CornerRadius = new CornerRadius(4),
                Padding = new Thickness(6, 2, 6, 2),
                Opacity = 0.0,
                Child = new TextBlock
                {
                    Text = $"{t.Index}:{t.Name}",
                    Foreground = Brushes.White,
                    FontSize = 11,
                    FontWeight = FontWeights.Bold
                }
            };

            double bx = drawBox ? t.Left + 4 : Math.Max(4, t.CenterX - 36);
            double by = drawBox ? t.Top + 4 : Math.Max(4, t.CenterY - 12);
            Canvas.SetLeft(badge, bx);
            Canvas.SetTop(badge, by);
            _badgeCanvas.Children.Add(badge);

            var fadeIn = new DoubleAnimation(0.0, 1.0, TimeSpan.FromMilliseconds(140));
            badge.BeginAnimation(UIElement.OpacityProperty, fadeIn);
        }

        if (!_badgeOverlay.IsVisible)
        {
            _badgeOverlay.Show();
        }
    }

    private void DispatchCommand(string utterance)
    {
        string msg = _router.HandleUtterance(utterance, out bool changed);
        StatusText.Text = msg;
        if (changed)
        {
            RefreshOverlayVisuals();
        }
    }

    private void EditorCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (EditorCombo.SelectedItem is string key)
        {
            _router.ActiveEditorKey = key;
        }
    }

    private void SectorsBtn_Click(object sender, RoutedEventArgs e) => DispatchCommand("show sectors");
    private void DragBtn_Click(object sender, RoutedEventArgs e) => DispatchCommand("drag");
    private void DropBtn_Click(object sender, RoutedEventArgs e) => DispatchCommand("drop");
    private void RunCmdBtn_Click(object sender, RoutedEventArgs e)
    {
        DispatchCommand(CommandBox.Text);
        CommandBox.Clear();
    }

    private void CommandBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
        {
            DispatchCommand(CommandBox.Text);
            CommandBox.Clear();
        }
    }

    private void QuitBtn_Click(object sender, RoutedEventArgs e)
    {
        CleanupAll();
        Close();
        Application.Current.Shutdown();
    }

    private void CleanupAll()
    {
        if (_cleanedUp) return;
        _cleanedUp = true;
        _router.ReleaseAll();
        try
        {
            if (_badgeOverlay.IsVisible)
            {
                _badgeOverlay.Hide();
            }
            _badgeOverlay.Close();
        }
        catch
        {
            // Ignore if overlay window was never shown
        }
    }
}
