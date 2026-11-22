import argparse
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox, QHBoxLayout, QComboBox

from core.input_windows import (
    check_target_window,
    send_key_combo,
    get_screen_size,
    move_mouse_to_screen,
    move_mouse_relative,
    mouse_click,
    mouse_double_click,
    mouse_down,
    mouse_up,
    mouse_scroll,
)
from core.nose_tracker import NoseTrackerWorker
from core.voice_worker import VoiceListenerWorker
from ui.plushie_overlay import PlushieOverlayWindow
from ui.theme_wizard import ThemeWizard
from ui.pack_builder import PackBuilderDialog
from ui.voice_grid import VoiceGridOverlay


WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "twenty one": 21, "twenty two": 22, "twenty three": 23, "twenty four": 24, "twenty five": 25,
    "twenty six": 26, "twenty seven": 27, "twenty eight": 28, "twenty nine": 29, "thirty": 30,
    "thirty one": 31, "thirty two": 32, "thirty three": 33, "thirty four": 34, "thirty five": 35,
    "thirty six": 36, "thirty seven": 37, "thirty eight": 38, "thirty nine": 39, "forty": 40,
    "forty one": 41, "forty two": 42, "forty three": 43, "forty four": 44, "forty five": 45,
    "forty six": 46, "forty seven": 47, "forty eight": 48,
}


class PlushieController:
    """Connects overlay, numbered voice grid, continuous mover, keyboard nav, face tracker, and input sender."""

    def __init__(self, root_dir: Path, enable_voice: bool = True):
        self.root_dir = Path(root_dir)
        self.enable_voice = enable_voice

        self.overlay = PlushieOverlayWindow(self.root_dir)
        self.grid_overlay = VoiceGridOverlay(cols=8, rows=6)

        self._is_calibrating = False
        self.nose_worker = NoseTrackerWorker()
        self.nose_worker.calibration_state_changed.connect(self._on_calibration_state_changed)
        self.nose_worker.delta_ready.connect(self._on_nose_delta)
        self.nose_worker.status_changed.connect(self._on_voice_status)
        self.nose_worker.error_occurred.connect(self._on_voice_error)

        # Continuous directional cursor / wheel hold state
        self._cont_dir: Optional[Tuple[int, int]] = None
        self._cont_scroll: int = 0
        self._cont_speed: int = 6
        self._cont_timer = QTimer()
        self._cont_timer.setInterval(30)
        self._cont_timer.timeout.connect(self._on_continuous_tick)

        self._add_extra_controls()

        self._pending_confirm: Optional[dict] = None
        self.overlay.handle_utterance = self.on_utterance  # type: ignore[method-assign]

        self.voice_worker: Optional[VoiceListenerWorker] = None
        if self.enable_voice:
            vosk_dir = self.root_dir / "models" / "vosk"
            self.voice_worker = VoiceListenerWorker(
                get_settings=lambda: dict(self.overlay.engine.settings),
                vosk_model_dir=vosk_dir,
            )
            self.voice_worker.utterance_detected.connect(self.on_utterance)
            self.voice_worker.status_changed.connect(self._on_voice_status)
            self.voice_worker.error_occurred.connect(self._on_voice_error)
            self.voice_worker.start()

    def _add_extra_controls(self) -> None:
        layout = self.overlay.panel.layout()
        if layout is None:
            return

        row = QHBoxLayout()

        self.theme_combo = QComboBox()
        self._refresh_theme_combo()
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        row.addWidget(self.theme_combo)

        pack_btn = QPushButton("Pack Builder")
        pack_btn.clicked.connect(self.open_pack_builder)
        row.addWidget(pack_btn)

        wizard_btn = QPushButton("Theme Wizard")
        wizard_btn.clicked.connect(self.open_theme_wizard)
        row.addWidget(wizard_btn)

        self.grid_btn = QPushButton("Grid")
        self.grid_btn.clicked.connect(self.toggle_voice_grid)
        row.addWidget(self.grid_btn)

        self.nose_btn = QPushButton("Nose: Off")
        self.nose_btn.setCheckable(True)
        self.nose_btn.clicked.connect(self.toggle_nose_tracking)
        row.addWidget(self.nose_btn)

        layout.addLayout(row)

    def toggle_voice_grid(self) -> None:
        if self.grid_overlay.isVisible():
            self.grid_overlay.hide()
            self.overlay.status_label.setText("Voice grid hidden.")
        else:
            sw, sh = get_screen_size()
            self.grid_overlay.show_full_screen_grid(sw, sh)
            self.overlay.status_label.setText("Grid active (1–48): say a number, 'click 14', 'zoom grid', or 'hide grid'.")

    def toggle_nose_tracking(self, checked: Optional[bool] = None) -> None:
        active = self.nose_btn.isChecked() if checked is None else bool(checked)
        self.nose_btn.setChecked(active)
        if active:
            self.nose_btn.setText("Nose: On")
            self.nose_worker.start()
        else:
            self.nose_btn.setText("Nose: Off")
            self.nose_worker.stop()
            self.overlay.status_label.setText("Face tracking paused.")

    def _on_calibration_state_changed(self, calibrating: bool) -> None:
        self._is_calibrating = bool(calibrating)

    def _on_nose_delta(self, dx: int, dy: int) -> None:
        move_mouse_relative(dx, dy)

    def _on_continuous_tick(self) -> None:
        if self._cont_dir is not None:
            dx, dy = self._cont_dir
            move_mouse_relative(dx * self._cont_speed, dy * self._cont_speed)
        if self._cont_scroll != 0:
            mouse_scroll(self._cont_scroll)

    def _stop_continuous(self) -> None:
        self._cont_dir = None
        self._cont_scroll = 0
        if self._cont_timer.isActive():
            self._cont_timer.stop()

    def _extract_grid_number(self, text: str) -> Optional[int]:
        m = re.search(r"\b(\d{1,2})\b", text)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 48:
                return val
        cleaned = re.sub(r"[^a-z\s]", " ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for phrase, val in sorted(WORD_NUMBERS.items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"\b{re.escape(phrase)}\b", cleaned):
                return val
        return None

    def _refresh_theme_combo(self) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        themes_dir = self.root_dir / "themes"
        if themes_dir.exists():
            for d in sorted(themes_dir.iterdir()):
                if (d / "theme.json").exists():
                    self.theme_combo.addItem(d.name, d.name)
        active = self.overlay.engine.settings.get("active_theme", "re_leon")
        idx = self.theme_combo.findData(active)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.blockSignals(False)

    def _on_theme_changed(self) -> None:
        theme_id = self.theme_combo.currentData()
        if not theme_id:
            return
        self.overlay.engine.theme, self.overlay.engine.prompts = self.overlay.engine.load_theme(theme_id)
        self.overlay.engine.save_settings()
        self.overlay._apply_theme_and_modes()
        self.overlay.status_label.setText(self.overlay.engine.prompt("listening"))

    def open_pack_builder(self) -> None:
        dlg = PackBuilderDialog(self.root_dir, parent=self.overlay)
        dlg.exec()
        self.overlay.engine.profiles = self.overlay.engine._load_profiles()
        self.overlay.status_label.setText("Command packs reloaded.")

    def open_theme_wizard(self) -> None:
        wizard = ThemeWizard(self.root_dir, parent=self.overlay)
        if wizard.exec():
            self._refresh_theme_combo()
            active_id = self.overlay.engine.settings.get("active_theme", "re_leon")
            self.overlay.engine.theme, self.overlay.engine.prompts = self.overlay.engine.load_theme(active_id)
            self.overlay._apply_theme_and_modes()
            self.overlay.status_label.setText(self.overlay.engine.prompt("listening"))

    def _on_voice_status(self, msg: str) -> None:
        self.overlay.status_label.setText(msg)

    def _on_voice_error(self, err: str) -> None:
        if self.nose_btn.isChecked() and ("webcam" in err.lower() or "cv2" in err.lower() or "face" in err.lower()):
            self.nose_btn.setChecked(False)
            self.nose_btn.setText("Nose: Off")
        self.overlay.status_label.setText(f"Voice/Cursor notice: {err}")

    def _handle_cursor_utterance(self, utterance: str) -> Optional[dict]:
        text = re.sub(r"\s+", " ", utterance.lower()).strip()
        step = 180 if any(w in text for w in ("far", "big", "lot", "fast")) else 60

        # 1. Stop continuous movement / hide grid
        if text in ("stop", "halt", "freeze", "stop moving", "stop scrolling"):
            was_moving = self._cont_dir is not None or self._cont_scroll != 0
            self._stop_continuous()
            if was_moving:
                return {"status": "cursor", "message": "Stopped continuous cursor/scroll motion."}

        # 2. Named UI / Numbered Grid Overlay commands
        if any(p in text for p in ("show grid", "open grid", "show numbers", "voice grid", "number grid")):
            sw, sh = get_screen_size()
            self.grid_overlay.show_full_screen_grid(sw, sh)
            return {"status": "cursor", "message": "Voice grid shown (1–48). Say a number or 'click 14'."}

        if any(p in text for p in ("zoom grid", "micro grid", "fine grid", "zoom numbers")):
            sw, sh = get_screen_size()
            pos = QCursor.pos()
            self.grid_overlay.show_micro_grid(sw, sh, pos.x(), pos.y(), box_size=240)
            return {"status": "cursor", "message": "Micro-grid (1–9) shown around cursor."}

        if any(p in text for p in ("hide grid", "close grid", "hide numbers", "clear grid")):
            self.grid_overlay.hide()
            return {"status": "cursor", "message": "Voice grid hidden."}

        if self.grid_overlay.isVisible() or text.startswith(("grid ", "cell ", "number ", "jump ", "click ")):
            cell_num = self._extract_grid_number(text)
            if cell_num is not None:
                if not self.grid_overlay.isVisible():
                    sw, sh = get_screen_size()
                    self.grid_overlay.show_full_screen_grid(sw, sh)
                target = self.grid_overlay.get_cell_center(cell_num)
                if target is not None:
                    move_mouse_to_screen(target[0], target[1])
                    if "right click" in text:
                        mouse_click("right")
                        self.grid_overlay.hide()
                        return {"status": "cursor", "message": f"Jumped to cell {cell_num} & right-clicked."}
                    if "double click" in text:
                        mouse_double_click()
                        self.grid_overlay.hide()
                        return {"status": "cursor", "message": f"Jumped to cell {cell_num} & double-clicked."}
                    if "click" in text or "tap" in text:
                        mouse_click("left")
                        self.grid_overlay.hide()
                        return {"status": "cursor", "message": f"Jumped to cell {cell_num} & clicked."}
                    if "keep" not in text:
                        self.grid_overlay.hide()
                    return {"status": "cursor", "message": f"Jumped to cell {cell_num} ({target[0]}, {target[1]})."}

        # 3. Continuous Directional Hold & Relative Wheel Modes
        if any(p in text for p in ("start moving", "keep moving", "glide", "drift")):
            if "left" in text:
                self._cont_dir = (-1, 0)
            elif "right" in text:
                self._cont_dir = (1, 0)
            elif "up" in text:
                self._cont_dir = (0, -1)
            elif "down" in text:
                self._cont_dir = (0, 1)
            if self._cont_dir is not None:
                self._cont_timer.start()
                return {"status": "cursor", "message": "Continuous cursor move started — say 'stop' to halt."}

        if any(p in text for p in ("keep scrolling", "start scrolling", "auto scroll")):
            if "up" in text:
                self._cont_scroll = 90
                self._cont_timer.start()
                return {"status": "cursor", "message": "Continuous scroll up — say 'stop' to halt."}
            if "down" in text:
                self._cont_scroll = -90
                self._cont_timer.start()
                return {"status": "cursor", "message": "Continuous scroll down — say 'stop' to halt."}

        if text in ("faster", "move faster", "speed up"):
            self._cont_speed = min(24, self._cont_speed + 4)
            return {"status": "cursor", "message": f"Cursor glide speed set to {self._cont_speed}."}
        if text in ("slower", "move slower", "slow down"):
            self._cont_speed = max(2, self._cont_speed - 3)
            return {"status": "cursor", "message": f"Cursor glide speed set to {self._cont_speed}."}

        # 4. Voice-Triggered Keyboard Navigation (no pointer needed)
        if text in ("shift tab", "back tab", "previous field"):
            ok, detail = send_key_combo(["shift", "tab"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("tab", "next field", "next item"):
            ok, detail = send_key_combo(["tab"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("arrow left", "step left", "previous frame"):
            ok, detail = send_key_combo(["left"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("arrow right", "step right", "next frame"):
            ok, detail = send_key_combo(["right"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("arrow up", "step up"):
            ok, detail = send_key_combo(["up"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("arrow down", "step down"):
            ok, detail = send_key_combo(["down"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("press enter", "hit enter", "enter key"):
            ok, detail = send_key_combo(["enter"])
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("press escape", "escape", "esc"):
            ok, detail = send_key_combo(["esc"])
            return {"status": "cursor", "message": detail if ok else detail}

        # 5. Face tracking & direct single-step cursor/click controls
        if text in ("nose on", "start nose", "enable nose"):
            self.toggle_nose_tracking(True)
            return {"status": "cursor", "message": "Face tracking enabled."}
        if text in ("nose off", "stop nose", "disable nose", "freeze cursor"):
            self.toggle_nose_tracking(False)
            return {"status": "cursor", "message": "Face tracking disabled."}
        if "recenter" in text or "reset nose" in text or "calibrate" in text:
            self.nose_worker.recenter()
            return {"status": "cursor", "message": "Restarting calibration..."}

        if "double click" in text:
            ok, detail = mouse_double_click()
            return {"status": "cursor", "message": detail if ok else detail}
        if "right click" in text:
            ok, detail = mouse_click("right")
            return {"status": "cursor", "message": detail if ok else detail}
        if any(k in text for k in ("hold click", "mouse down", "drag start")):
            ok, detail = mouse_down("left")
            return {"status": "cursor", "message": detail if ok else detail}
        if any(k in text for k in ("release", "mouse up", "drop", "let go")):
            ok, detail = mouse_up("left")
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("click", "left click", "tap"):
            ok, detail = mouse_click("left")
            return {"status": "cursor", "message": detail if ok else detail}

        if "scroll up" in text:
            ok, detail = mouse_scroll(360 if "fast" in text else 180)
            return {"status": "cursor", "message": detail if ok else detail}
        if "scroll down" in text:
            ok, detail = mouse_scroll(-360 if "fast" in text else -180)
            return {"status": "cursor", "message": detail if ok else detail}

        if "move left" in text or "go left" in text:
            ok, detail = move_mouse_relative(-step, 0)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move right" in text or "go right" in text:
            ok, detail = move_mouse_relative(step, 0)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move up" in text or "go up" in text:
            ok, detail = move_mouse_relative(0, -step)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move down" in text or "go down" in text:
            ok, detail = move_mouse_relative(0, step)
            return {"status": "cursor", "message": detail if ok else detail}

        return None

    def on_utterance(self, utterance: str, window_ok: Optional[bool] = None, text_input_focused: bool = False) -> dict:
        if self._is_calibrating:
            return {"status": "ignored", "message": "Ignored audio noise during calibration."}

        cursor_res = self._handle_cursor_utterance(utterance)
        if cursor_res is not None:
            self.overlay._apply_theme_and_modes()
            self.overlay.status_label.setText(cursor_res.get("message", ""))
            return cursor_res

        engine = self.overlay.engine
        app_key = engine.settings.get("active_app", "capcut")
        profile = engine.profiles.get(app_key, {})

        if window_ok is None:
            window_ok, _ = check_target_window(profile.get("window_keywords", []))

        result = engine.resolve_command(
            utterance=utterance,
            app_key=app_key,
            window_ok=window_ok,
            text_input_focused=text_input_focused,
        )

        status = result.get("status")
        if status == "execute":
            keys = result.get("keys", [])
            if result.get("requires_confirm"):
                self._pending_confirm = result
                msg = f"Confirm '{result.get('command')}' [{'+'.join(keys)}]? Click Yes to run."
                self.overlay._apply_theme_and_modes()
                self.overlay.status_label.setText(msg)
                reply = QMessageBox.question(
                    self.overlay,
                    "Confirm Action",
                    msg,
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.overlay.status_label.setText("Cancelled action.")
                    return {"status": "cancelled", "message": "Cancelled action."}

            ok, detail = send_key_combo(keys)
            if not ok:
                refusal = engine.prompt(
                    "cant_do_unsupported",
                    action=result.get("command", utterance),
                    app=profile.get("app_name", app_key.title()),
                )
                self.overlay._apply_theme_and_modes()
                self.overlay.status_label.setText(f"{refusal} ({detail})")
                return {"status": "cant_do", "message": refusal}

        self.overlay._apply_theme_and_modes()
        self.overlay.status_label.setText(result.get("message", ""))
        return result

    def shutdown(self) -> None:
        self._stop_continuous()
        self.grid_overlay.close()
        self.nose_worker.stop()
        if self.voice_worker is not None:
            self.voice_worker.stop()
        self.overlay.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Plushie Editor Overlay")
    parser.add_argument("--no-voice", action="store_true", help="Run UI/theme/wizard without microphone loop")
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parent
    app = QApplication(sys.argv)
    controller = PlushieController(root_dir=root_dir, enable_voice=not args.no_voice)
    controller.overlay.show()
    exit_code = app.exec()
    controller.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
