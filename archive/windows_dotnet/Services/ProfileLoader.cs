using System.IO;
using System.Text.Json;

namespace VoicePlushie.Services;

public sealed class CommandEntry
{
    public List<string> Aliases { get; set; } = new();
    public List<string> Keys { get; set; } = new();
    public bool Supported { get; set; } = true;
    public bool RequiresConfirm { get; set; } = false;
    public string Reason { get; set; } = string.Empty;
}

public sealed class EditorProfile
{
    public string AppName { get; set; } = "Clipchamp";
    public List<string> WindowKeywords { get; set; } = new();
    public Dictionary<string, CommandEntry> Commands { get; set; } = new();
}

public static class ProfileLoader
{
    public static Dictionary<string, EditorProfile> LoadProfiles(string profilesDir)
    {
        var result = new Dictionary<string, EditorProfile>(StringComparer.OrdinalIgnoreCase);
        if (!Directory.Exists(profilesDir))
        {
            return result;
        }

        var options = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        foreach (var file in Directory.EnumerateFiles(profilesDir, "*.json").OrderBy(f => f))
        {
            try
            {
                var json = File.ReadAllText(file);
                var profile = JsonSerializer.Deserialize<EditorProfile>(json, options);
                if (profile != null)
                {
                    var key = Path.GetFileNameWithoutExtension(file).ToLowerInvariant();
                    result[key] = profile;
                }
            }
            catch
            {
                // Skip malformed profile file
            }
        }

        return result;
    }
}
