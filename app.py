import argparse
import re
import sys
from pathlib import Path
from typing import Optional

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


class PlushieController:
    """Connects the plushie overlay, pack builder, theme wizard, voice listener, face tracker, and input sender."""

    def __init__(self, root_dir: Path, enable_voice: bool = True):
        self.root_dir = Path(root_dir)
        self.enable_voice = enable_voice

        self.overlay = PlushieOverlayWindow(self.root_dir)
        sw, sh = get_screen_size()
        self.nose_worker = NoseTrackerWorker(screen_width=sw, screen_height=sh, calibration_seconds=5.0)
        self.nose_worker.screen_pos_ready.connect(self._on_face_screen_pos)
        self.nose_worker.status_changed.connect(self._on_voice_status)
        self.nose_worker.error_occurred.connect(self._on_voice_error)

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

        self.nose_btn = QPushButton("Nose: Off")
        self.nose_btn.setCheckable(True)
        self.nose_btn.clicked.connect(self.toggle_nose_tracking)
        row.addWidget(self.nose_btn)

        layout.addLayout(row)

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

    def _on_face_screen_pos(self, x: int, y: int) -> None:
        move_mouse_to_screen(x, y)

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

        if text in ("nose on", "start nose", "enable nose"):
            self.toggle_nose_tracking(True)
            return {"status": "cursor", "message": "Face tracking enabled (5s calibration)."}
        if text in ("nose off", "stop nose", "disable nose", "freeze cursor"):
            self.toggle_nose_tracking(False)
            return {"status": "cursor", "message": "Face tracking disabled."}
        if "recenter" in text or "reset nose" in text or "calibrate" in text:
            self.nose_worker.recenter()
            return {"status": "cursor", "message": "Starting 5s calibration..."}

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
            ok, detail = mouse_scroll(240)
            return {"status": "cursor", "message": detail if ok else detail}
        if "scroll down" in text:
            ok, detail = mouse_scroll(-240)
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
