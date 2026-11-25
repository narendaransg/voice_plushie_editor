using System.Speech.Recognition;

namespace VoicePlushie.Services;

public sealed class VoiceService : IDisposable
{
    private SpeechRecognitionEngine? _recognizer;
    private bool _listening;

    public event Action<string>? UtteranceHeard;
    public event Action<string>? StatusUpdated;

    public bool IsListening => _listening;

    public void Start()
    {
        if (_listening) return;

        try
        {
            _recognizer = new SpeechRecognitionEngine();
            _recognizer.SetInputToDefaultAudioDevice();

            var choices = new Choices(new[]
            {
                "show sectors", "show labels", "sectors", "hide", "hide labels", "hide sectors",
                "go up", "level up", "back", "go back",
                "drag", "drag it", "grab", "drop", "paste", "place", "release",
                "click", "left click", "double click", "right click",
                "hover left", "hover right", "hover up", "hover down",
                "nudge left", "nudge right", "tiny left", "tiny right",
                "move left", "move right", "move up", "move down",
                "stop", "halt", "split", "cut", "undo", "redo", "play", "pause",
                "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve"
            });

            var gb = new GrammarBuilder(choices);
            _recognizer.LoadGrammar(new Grammar(gb));
            _recognizer.SpeechRecognized += OnSpeechRecognized;
            _recognizer.RecognizeAsync(RecognizeMode.Multiple);
            _listening = true;
            StatusUpdated?.Invoke("Mic listening (Windows Speech grammar active)...");
        }
        catch (Exception ex)
        {
            _listening = false;
            StatusUpdated?.Invoke($"Mic unavailable: {ex.Message}");
        }
    }

    private void OnSpeechRecognized(object? sender, SpeechRecognizedEventArgs e)
    {
        if (!_listening || e.Result == null || e.Result.Confidence < 0.25f)
        {
            return;
        }
        var text = e.Result.Text.Trim();
        if (!string.IsNullOrWhiteSpace(text))
        {
            UtteranceHeard?.Invoke(text);
        }
    }

    public void Stop()
    {
        _listening = false;
        if (_recognizer != null)
        {
            try
            {
                _recognizer.SpeechRecognized -= OnSpeechRecognized;
                _recognizer.RecognizeAsyncCancel();
                _recognizer.Dispose();
            }
            catch
            {
                // Ignore cleanup errors
            }
            finally
            {
                _recognizer = null;
            }
        }
    }

    public void Dispose() => Stop();
}
