using System.Diagnostics;
using System.IO;
using System.Text;

namespace VoicePlushie.Services;

public sealed class VoiceService : IDisposable
{
    private readonly string _repoRoot;
    private Process? _workerProcess;
    private bool _listening;

    public event Action<string>? UtteranceHeard;
    public event Action<string>? StatusUpdated;

    public VoiceService(string repoRoot)
    {
        _repoRoot = repoRoot;
    }

    public bool IsListening => _listening;

    public void Start()
    {
        if (_listening) return;

        var voskDir = Path.Combine(_repoRoot, "models", "vosk");
        var pythonExe = FindPythonExecutable();
        var scriptPath = EnsureVoskHelperScript();

        if (pythonExe == null || !Directory.Exists(voskDir))
        {
            _listening = false;
            StatusUpdated?.Invoke("Voice worker ready (use Mic toggle once Python+Vosk or model at models/vosk is available; type/click commands work now).");
            return;
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = pythonExe,
                Arguments = $"\"{scriptPath}\" \"{voskDir}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                StandardOutputEncoding = Encoding.UTF8
            };

            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            proc.OutputDataReceived += (_, args) =>
            {
                if (string.IsNullOrWhiteSpace(args.Data)) return;
                var line = args.Data.Trim();
                if (line.StartsWith("STATUS:", StringComparison.Ordinal))
                {
                    StatusUpdated?.Invoke(line["STATUS:".Length..].Trim());
                }
                else if (line.StartsWith("UTTERANCE:", StringComparison.Ordinal))
                {
                    var text = line["UTTERANCE:".Length..].Trim();
                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        UtteranceHeard?.Invoke(text);
                    }
                }
            };
            proc.ErrorDataReceived += (_, args) =>
            {
                if (!string.IsNullOrWhiteSpace(args.Data))
                {
                    StatusUpdated?.Invoke($"Voice note: {args.Data.Trim()}");
                }
            };

            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            _workerProcess = proc;
            _listening = true;
            StatusUpdated?.Invoke("Mic listening (Vosk local worker)...");
        }
        catch (Exception ex)
        {
            _listening = false;
            StatusUpdated?.Invoke($"Mic unavailable ({ex.Message}) — type/click commands work now.");
        }
    }

    private string? FindPythonExecutable()
    {
        var userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        var candidates = new[]
        {
            Path.Combine(userProfile, "voice_plushie_venv", "Scripts", "python.exe"),
            "python",
            "python3"
        };

        foreach (var cand in candidates)
        {
            if (cand.Contains(Path.DirectorySeparatorChar))
            {
                if (File.Exists(cand)) return cand;
            }
            else
            {
                try
                {
                    using var p = Process.Start(new ProcessStartInfo
                    {
                        FileName = cand,
                        Arguments = "--version",
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true
                    });
                    if (p != null)
                    {
                        p.WaitForExit(1500);
                        if (p.ExitCode == 0) return cand;
                    }
                }
                catch
                {
                    // Try next candidate
                }
            }
        }
        return null;
    }

    private string EnsureVoskHelperScript()
    {
        var helperDir = Path.Combine(_repoRoot, "windows_winui3", "Services");
        Directory.CreateDirectory(helperDir);
        var helperPath = Path.Combine(helperDir, "vosk_mic_worker.py");
        if (!File.Exists(helperPath))
        {
            const string code = """
import json
import queue
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("STATUS: Missing Vosk model path", flush=True)
        return 1

    model_dir = Path(sys.argv[1])
    if not model_dir.exists():
        print(f"STATUS: Vosk model not found at {model_dir}", flush=True)
        return 1

    try:
        import sounddevice as sd
        import vosk
    except Exception as exc:
        print(f"STATUS: Missing sounddevice/vosk ({exc})", flush=True)
        return 1

    vosk.SetLogLevel(-1)
    model = vosk.Model(str(model_dir))
    rec = vosk.KaldiRecognizer(model, 16000)
    audio_q: "queue.Queue[bytes]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        _ = frames, time_info, status
        if indata is not None:
            try:
                audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

    print("STATUS: Mic active (Vosk local grammar)...", flush=True)
    try:
        with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype="int16", channels=1, callback=callback):
            while True:
                data = audio_q.get()
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result() or "{}")
                    text = str(res.get("text") or "").strip()
                    if text and text != "[unk]":
                        print(f"UTTERANCE:{text}", flush=True)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"STATUS: Mic error ({exc})", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
""";
            File.WriteAllText(helperPath, code, Encoding.UTF8);
        }
        return helperPath;
    }

    public void Stop()
    {
        _listening = false;
        if (_workerProcess != null)
        {
            try
            {
                if (!_workerProcess.HasExited)
                {
                    _workerProcess.Kill(entireProcessTree: true);
                    _workerProcess.WaitForExit(1000);
                }
            }
            catch
            {
                // Ignore process exit errors
            }
            finally
            {
                _workerProcess.Dispose();
                _workerProcess = null;
            }
        }
    }

    public void Dispose() => Stop();
}
