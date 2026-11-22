import argparse
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox

from core.input_windows import check_target_window, send_key_combo
from core.voice_worker import VoiceListenerWorker
from ui.plushie_overlay import PlushieOverlayWindow
from ui.theme_wizard import ThemeWizard


class PlushieController:
    """Connects the plushie overlay, theme wizard, voice listener, and input sender."""

    def __init__(self, root_dir: Path, enable_voice: bool = True):
        self.root_dir = Path(root_dir)
        self.enable_voice = enable_voice

        self.overlay = PlushieOverlayWindow(self.root_dir)
        self._add_wizard_button()

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

    def _add_wizard_button(self) -> None:
        wizard_btn = QPushButton("Theme Wizard")
        wizard_btn.clicked.connect(self.open_theme_wizard)
        layout = self.overlay.panel.layout()
        if layout is not None:
            layout.addWidget(wizard_btn)

    def open_theme_wizard(self) -> None:
        wizard = ThemeWizard(self.root_dir, parent=self.overlay)
        if wizard.exec():
            active_id = self.overlay.engine.settings.get("active_theme", "re_leon")
            self.overlay.engine.load_theme(active_id)
            self.overlay._apply_theme_and_modes()
            self.overlay.status_label.setText(self.overlay.engine.prompt("listening"))

    def _on_voice_status(self, msg: str) -> None:
        self.overlay.status_label.setText(msg)

    def _on_voice_error(self, err: str) -> None:
        self.overlay.status_label.setText(f"Voice notice: {err}")

    def on_utterance(self, utterance: str, window_ok: Optional[bool] = None, text_input_focused: bool = False) -> dict:
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
                msg = f"Confirm '{result.get('command')}' [{ '+'.join(keys) }]? Click Yes or say confirm."
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
