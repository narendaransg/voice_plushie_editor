import json
import queue
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Signal


COMMAND_GRAMMAR: List[str] = [
    "stop", "halt", "freeze", "stop moving", "stop scrolling",
    "show sectors", "show labels", "sectors", "hide", "hide labels", "hide sectors",
    "go up", "level up", "back", "go back", "previous level",
    "go down", "drill down", "zoom", "deeper", "go to",
    "click", "left click", "double click", "right click", "tap",
    "drag it", "drag this", "drag", "grab it", "grab",
    "drop", "paste", "place", "release", "let go",
    "hover left", "hover right", "nudge left", "nudge right",
    "tiny left", "tiny right", "scrub left", "scrub right",
    "move left", "move right", "move up", "move down",
    "go left", "go right", "go up", "go down",
    "start moving left", "start moving right", "start moving up", "start moving down",
    "keep scrolling up", "keep scrolling down", "scroll up", "scroll down",
    "faster", "slower", "speed up", "slow down",
    "split", "cut", "undo", "redo", "play", "pause", "zoom in", "zoom out",
    "what is", "what does", "describe", "rescan", "scan app",
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "[unk]",
]


class VoiceListenerWorker(QObject):
    """Background voice listener supporting GPU/CPU, Vosk grammar biasing, Whisper fallback, and Always-On/Wake modes."""

    utterance_detected = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        get_settings: Callable[[], Dict[str, Any]],
        sample_rate: int = 16000,
        chunk_seconds: float = 1.6,
        vosk_model_dir: Optional[Path] = None,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.get_settings = get_settings
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.vosk_model_dir = Path(vosk_model_dir) if vosk_model_dir else None

        self._stop_event = threading.Event()
        self._muted = False
        self._thread: Optional[threading.Thread] = None
        self._audio_q: "queue.Queue[bytes]" = queue.Queue()

        self._whisper_model = None
        self._whisper_sig = None
        self._whisper_unavailable = False
        self._vosk_model = None

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)

    def is_muted(self) -> bool:
        return self._muted

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break
        self._thread = threading.Thread(target=self._run_loop, name="VoiceListenerThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        _ = frames, time_info, status
        if not self._stop_event.is_set() and not self._muted and indata is not None:
            try:
                self._audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

    def _ensure_whisper(self, mode: str):
        if self._whisper_unavailable:
            return None
        sig = ("gpu", "small", "float16") if mode == "gpu" else ("cpu", "tiny", "int8")
        if self._whisper_model is not None and self._whisper_sig == sig:
            return self._whisper_model

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except Exception:
            self._whisper_unavailable = True
            return None

        device = "cuda" if sig[0] == "gpu" else "cpu"
        compute_type = sig[2]
        self.status_changed.emit(f"Loading Whisper ({sig[1]} / {device})...")
        self._whisper_model = WhisperModel(sig[1], device=device, compute_type=compute_type)
        self._whisper_sig = sig
        return self._whisper_model

    def _ensure_vosk(self):
        if self._vosk_model is not None:
            return self._vosk_model
        if not self.vosk_model_dir or not self.vosk_model_dir.exists():
            return None
        try:
            import vosk  # type: ignore
            vosk.SetLogLevel(-1)
            self.status_changed.emit("Loading Vosk model...")
            self._vosk_model = vosk.Model(str(self.vosk_model_dir))
            return self._vosk_model
        except Exception as exc:
            self.error_occurred.emit(f"Failed to load Vosk model: {exc}")
            return None

    def _transcribe_with_vosk(self, pcm_bytes: bytes) -> str:
        model = self._ensure_vosk()
        if model is None:
            return ""
        try:
            from vosk import KaldiRecognizer  # type: ignore
            try:
                rec = KaldiRecognizer(model, self.sample_rate, json.dumps(COMMAND_GRAMMAR))
            except TypeError:
                rec = KaldiRecognizer(model, self.sample_rate)
            rec.AcceptWaveform(pcm_bytes)
            res = json.loads(rec.FinalResult() or "{}")
            text = str(res.get("text") or "").strip()
            return "" if text == "[unk]" else text
        except Exception as exc:
            self.error_occurred.emit(f"Vosk transcription error: {exc}")
            return ""

    def _transcribe_pcm(self, pcm_bytes: bytes, mode: str) -> str:
        import numpy as np

        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio_int16.size == 0:
            return ""
        rms = float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2)))
        if rms < 220.0:
            return ""

        has_vosk_dir = bool(self.vosk_model_dir and self.vosk_model_dir.exists())
        if mode == "gpu" and not self._whisper_unavailable:
            model = self._ensure_whisper("gpu")
            if model is not None:
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                segments, _ = model.transcribe(audio_float32, beam_size=1, vad_filter=True)
                spoken = " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
                if spoken:
                    return spoken

        if has_vosk_dir:
            return self._transcribe_with_vosk(pcm_bytes)

        model = self._ensure_whisper(mode)
        if model is not None:
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            segments, _ = model.transcribe(audio_float32, beam_size=1, vad_filter=True)
            return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()

        return ""

    def _apply_voice_mode_gate(self, text: str, settings: Dict[str, Any]) -> Tuple[Optional[str], str]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return None, "Mic listening (no speech detected)"

        voice_mode = settings.get("voice_mode", "always_on")
        if voice_mode == "always_on":
            return cleaned, f"Heard: '{cleaned}'"

        wake = (settings.get("wake_phrase") or "leon").strip().lower()
        lowered = cleaned.lower()
        if wake and wake in lowered:
            stripped = re.sub(rf"\b{re.escape(wake)}\b", "", lowered, flags=re.IGNORECASE).strip(" ,.!?")
            final_text = stripped if stripped else cleaned
            return final_text, f"Wake '{wake}' heard: '{final_text}'"

        return None, f"Heard '{cleaned}' (waiting for wake word '{wake}')"

    def _run_loop(self) -> None:
        try:
            import sounddevice as sd  # type: ignore
        except Exception as exc:
            self.error_occurred.emit(f"Audio capture unavailable ('sounddevice' missing): {exc}")
            return

        has_vosk_dir = bool(self.vosk_model_dir and self.vosk_model_dir.exists())
        if not has_vosk_dir and self._whisper_unavailable:
            self.error_occurred.emit(f"Vosk model folder missing at {self.vosk_model_dir}")
            return

        device_idx = None
        try:
            cfg = self.get_settings() or {}
            device_idx = cfg.get("mic_device_index", None)
        except Exception:
            device_idx = None

        frames_per_chunk = max(1600, int(self.sample_rate * self.chunk_seconds))
        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=frames_per_chunk,
                device=device_idx,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            ):
                self.status_changed.emit("Mic active — speak commands or numbers...")
                while not self._stop_event.is_set():
                    try:
                        pcm_bytes = self._audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if self._muted:
                        continue

                    settings = self.get_settings() or {}
                    mode = str(settings.get("compute_mode", "cpu")).lower()

                    try:
                        raw_text = self._transcribe_pcm(pcm_bytes, mode)
                    except Exception as exc:
                        self.error_occurred.emit(f"STT error ({mode}): {exc}")
                        continue

                    routed, feedback = self._apply_voice_mode_gate(raw_text, settings)
                    if routed:
                        self.utterance_detected.emit(routed)
                    else:
                        self.status_changed.emit(feedback)
        except Exception as exc:
            self.error_occurred.emit(f"Microphone stream error: {exc}")
