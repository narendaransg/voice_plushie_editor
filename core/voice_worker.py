import json
import queue
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QThread, Signal


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


class VoiceListenerWorker(QThread):
    utterance_detected = Signal(str)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        get_settings: Callable[[], Dict[str, Any]],
        vosk_model_dir: Path,
        parent: Optional[Any] = None,
    ):
        super().__init__(parent)
        self.get_settings = get_settings
        self.vosk_model_dir = Path(vosk_model_dir)
        self._running = False
        self._audio_q: "queue.Queue[bytes]" = queue.Queue()

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        _ = frames, time_info, status
        if self._running and indata is not None:
            try:
                self._audio_q.put_nowait(bytes(indata))
            except queue.Full:
                pass

    def run(self) -> None:
        if not self.vosk_model_dir.exists():
            self.error_occurred.emit(f"Vosk model folder missing at {self.vosk_model_dir}")
            return

        try:
            import sounddevice as sd  # type: ignore
            import vosk  # type: ignore
        except Exception as exc:
            self.error_occurred.emit(f"Audio/Vosk import failed: {exc}")
            return

        try:
            vosk.SetLogLevel(-1)
            model = vosk.Model(str(self.vosk_model_dir))
            samplerate = 16000
            try:
                rec = vosk.KaldiRecognizer(model, samplerate, json.dumps(COMMAND_GRAMMAR))
            except TypeError:
                rec = vosk.KaldiRecognizer(model, samplerate)
        except Exception as exc:
            self.error_occurred.emit(f"Failed to load Vosk model: {exc}")
            return

        self._running = True
        self.status_changed.emit("Mic listening (command grammar active)...")

        device_idx = None
        try:
            cfg = self.get_settings() or {}
            device_idx = cfg.get("mic_device_index", None)
        except Exception:
            device_idx = None

        try:
            with sd.RawInputStream(
                samplerate=samplerate,
                blocksize=4000,
                device=device_idx,
                dtype="int12" if False else "int16",
                channels=1,
                callback=self._audio_callback,
            ):
                while self._running:
                    try:
                        data = self._audio_q.get(timeout=0.1)
                    except queue.Empty:
                        continue

                    if rec.AcceptWaveform(data):
                        res = json.loads(rec.Result() or "{}")
                        text = str(res.get("text") or "").strip()
                        if text and text != "[unk]":
                            self.utterance_detected.emit(text)
                    else:
                        part = json.loads(rec.PartialResult() or "{}")
                        p_text = str(part.get("partial") or "").strip().lower()
                        if p_text in ("stop", "halt", "freeze", "drop", "paste", "hide"):
                            rec.Reset()
                            self.utterance_detected.emit(p_text)
        except Exception as exc:
            self.error_occurred.emit(f"Mic stream error: {exc}")
        finally:
            self._running = False
