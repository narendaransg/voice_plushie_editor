import json
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal


class VoiceListenerWorker(QObject):
    """Background voice listener supporting GPU/CPU and Always-On/Wake-Phrase modes."""

    utterance_detected = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        get_settings: Callable[[], dict],
        sample_rate: int = 16000,
        chunk_seconds: float = 2.5,
        vosk_model_dir: Optional[Path] = None,
    ):
        super().__init__(None)
        self.get_settings = get_settings
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.vosk_model_dir = vosk_model_dir

        self._stop_event = threading.Event()
        self._muted = False
        self._thread: Optional[threading.Thread] = None
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
        self._thread = threading.Thread(target=self._run_loop, name="VoiceListenerThread", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _ensure_whisper(self, mode: str):
        if self._whisper_unavailable:
            return None
        sig = ("gpu", "small", "float16") if mode == "gpu" else ("cpu", "tiny", "int8")
        if self._whisper_model is not None and self._whisper_sig == sig:
            return self._whisper_model

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            self._whisper_unavailable = True
            self.status_changed.emit(f"Whisper unavailable ({exc}); using Vosk / offline fallback.")
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
        from vosk import Model

        if not self.vosk_model_dir or not self.vosk_model_dir.exists():
            return None
        self.status_changed.emit("Loading Vosk offline CPU model...")
        self._vosk_model = Model(str(self.vosk_model_dir))
        return self._vosk_model

    def _transcribe_pcm(self, pcm_bytes: bytes, mode: str) -> str:
        if mode == "cpu" and self.vosk_model_dir and self.vosk_model_dir.exists():
            from vosk import KaldiRecognizer

            model = self._ensure_vosk()
            if model is not None:
                rec = KaldiRecognizer(model, self.sample_rate)
                rec.AcceptWaveform(pcm_bytes)
                res = json.loads(rec.FinalResult())
                return res.get("text", "").strip()

        import numpy as np

        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio_int16.size == 0:
            return ""
        rms = float(np.sqrt(np.mean(audio_int16.astype(np.float32) ** 2)))
        if rms < 250.0:
            return ""

        model = self._ensure_whisper(mode)
        if model is None:
            return ""

        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio_float32, beam_size=1, vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()

    def _apply_voice_mode_gate(self, text: str, settings: dict) -> Optional[str]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned:
            return None

        voice_mode = settings.get("voice_mode", "always_on")
        if voice_mode == "always_on":
            return cleaned

        wake = (settings.get("wake_phrase") or "leon").strip().lower()
        lowered = cleaned.lower()
        if wake and wake in lowered:
            stripped = re.sub(rf"\b{re.escape(wake)}\b", "", lowered, flags=re.IGNORECASE).strip(" ,.!?")
            return stripped if stripped else cleaned
        return None

    def _run_loop(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:
            self.error_occurred.emit(f"Audio capture unavailable ('sounddevice' missing): {exc}")
            return

        frames_per_chunk = int(self.sample_rate * self.chunk_seconds)
        try:
            with sd.RawInputStream(
                samplerate=self.sample_rate,
                blocksize=frames_per_chunk,
                dtype="int16",
                channels=1,
            ) as stream:
                self.status_changed.emit("Microphone active.")
                while not self._stop_event.is_set():
                    data, overflowed = stream.read(frames_per_chunk)
                    if overflowed:
                        continue
                    if self._muted:
                        continue

                    settings = self.get_settings()
                    mode = settings.get("compute_mode", "cpu").lower()
                    pcm_bytes = bytes(data)

                    try:
                        raw_text = self._transcribe_pcm(pcm_bytes, mode)
                    except Exception as exc:
                        self.error_occurred.emit(f"STT error ({mode}): {exc}")
                        continue

                    routed = self._apply_voice_mode_gate(raw_text, settings)
                    if routed:
                        self.utterance_detected.emit(routed)
        except Exception as exc:
            self.error_occurred.emit(f"Microphone stream error: {exc}")
