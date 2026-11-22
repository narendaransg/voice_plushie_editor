import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QTimer
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
from core.tool_scanner import scan_active_tool_and_map, enrich_with_web_knowledge
from core.voice_worker import VoiceListenerWorker
from ui.plushie_overlay import PlushieOverlayWindow
from ui.theme_wizard import ThemeWizard
from ui.pack_builder import PackBuilderDialog
from ui.interactive_labels import InteractiveLabelOverlay


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
    "forty six": 46, "forty seven": 47, "forty eight": 48, "forty nine": 49, "fifty": 50,
}


class PlushieController:
    """Connects overlay, startup tool scanner + knowledge map, multi-level labels, mover, keyboard nav, and voice."""

    def __init__(self, root_dir: Path, enable_voice: bool = True):
        self.root_dir = Path(root_dir)
        self.enable_voice = enable_voice
        self.scan_file = self.root_dir / "ui" / "active_tool_map.json"
        self.tool_map: Dict[str, Any] = {}

        self.overlay = PlushieOverlayWindow(self.root_dir)
        self.label_overlay = InteractiveLabelOverlay(scan_file=self.scan_file)

        self._cont_dir: Optional[Tuple[int, int]] = None
        self._cont_scroll: int = 0
        self._cont_speed: int = 6
        self._cont_timer = QTimer()
        self._cont_timer.setInterval(30)
        self._cont_timer.timeout.connect(self._on_continuous_tick)

        self._add_extra_controls()

        self._pending_confirm: Optional[dict] = None
        self.overlay.handle_utterance = self.on_utterance  # type: ignore[method-assign]

        # Run startup scan on current tool & map with video editor knowledge
        self.run_tool_scan(announce=True)

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

    def run_tool_scan(self, announce: bool = False) -> Dict[str, Any]:
        self.tool_map = scan_active_tool_and_map(self.scan_file)
        tool_name = self.tool_map.get("detected_tool", "Active Editor")
        ctrl_count = self.tool_map.get("uia_control_count", 0)
        if announce:
            self.overlay.status_label.setText(
                f"Scanned '{tool_name}' ({ctrl_count} UI controls + editor map ready)."
            )
        return self.tool_map

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

        self.labels_btn = QPushButton("Sectors")
        self.labels_btn.clicked.connect(self.toggle_interactive_labels)
        row.addWidget(self.labels_btn)

        layout.addLayout(row)

    def toggle_interactive_labels(self) -> None:
        if self.label_overlay.isVisible():
            self.label_overlay.clear_labels()
            self.overlay.status_label.setText("Sector labels hidden.")
        else:
            self.run_tool_scan(announce=False)
            sw, sh = get_screen_size()
            count = self.label_overlay.show_sectors(sw, sh)
            tool_name = self.tool_map.get("detected_tool", "Editor")
            self.overlay.status_label.setText(
                f"{tool_name}: {count} sectors shown — say 'go to sector 2', 'what is 2', or 'hide labels'."
            )

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

    def _extract_target_number(self, text: str) -> Optional[int]:
        m = re.search(r"\b(\d{1,2})\b", text)
        if m:
            return int(m.group(1))
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
        self.overlay.status_label.setText(f"Voice notice: {err}")

    def _handle_cursor_utterance(self, utterance: str) -> Optional[dict]:
        text = re.sub(r"\s+", " ", utterance.lower()).strip()
        step = 180 if any(w in text for w in ("far", "big", "lot", "fast")) else 60

        # 0. Rescan active tool & map
        if any(p in text for p in ("rescan", "scan app", "scan tool", "refresh map")):
            info = self.run_tool_scan(announce=False)
            return {
                "status": "cursor",
                "message": f"Rescanned '{info.get('detected_tool', 'Editor')}' ({info.get('uia_control_count', 0)} controls).",
            }

        # 1. Stop continuous movement / scroll
        if text in ("stop", "halt", "freeze", "stop moving", "stop scrolling"):
            was_moving = self._cont_dir is not None or self._cont_scroll != 0
            self._stop_continuous()
            if was_moving:
                return {"status": "cursor", "message": "Stopped continuous cursor/scroll motion."}

        # 2. Multi-level Sector & Control Navigation
        if any(p in text for p in ("show labels", "show sectors", "label controls", "show buttons", "sectors")):
            self.run_tool_scan(announce=False)
            sw, sh = get_screen_size()
            count = self.label_overlay.show_sectors(sw, sh)
            return {
                "status": "cursor",
                "message": f"{count} sectors shown — say 'go to sector 2', 'what is 2', or 'hide labels'.",
            }

        if any(p in text for p in ("hide labels", "close labels", "hide targets", "clear labels", "hide sectors")):
            self.label_overlay.clear_labels()
            return {"status": "cursor", "message": "Labels hidden."}

        if text in ("back sector", "go back", "previous level", "level up") and self.label_overlay.isVisible():
            prev = self.label_overlay.go_back_level()
            if prev:
                return {"status": "cursor", "message": f"Returned to {prev}."}
            return {"status": "cursor", "message": "Exited sector labels."}

        # Ask what a tool/tab/sector/control does even if labels aren't currently shown
        if any(q in text for q in ("what is", "what does", "describe", "purpose", "use of")):
            if self.label_overlay.isVisible():
                num = self._extract_target_number(text)
                target = (
                    self.label_overlay.get_target_by_number(num)
                    if num is not None
                    else self.label_overlay.get_target_by_name(text)
                )
                if target is not None:
                    return {"status": "cursor", "message": f"#{target.index} {target.name}: {target.purpose}"}
            mapped = enrich_with_web_knowledge(text)
            if mapped["matched_topic"] != text:
                return {"status": "cursor", "message": f"{mapped['matched_topic']}: {mapped['purpose']}"}

        if self.label_overlay.isVisible():
            num = self._extract_target_number(text)
            target = (
                self.label_overlay.get_target_by_number(num)
                if num is not None
                else self.label_overlay.get_target_by_name(text)
            )

            if target is not None:
                sw, sh = get_screen_size()
                cx, cy = target.center

                wants_zoom = any(w in text for w in ("sector", "go to", "zoom", "deeper", "inside", "open"))
                if target.kind == "sector" and ("click" not in text):
                    sub_count = self.label_overlay.drill_into_target(target, sw, sh)
                    return {
                        "status": "cursor",
                        "message": f"Inside '{target.name}' ({sub_count} items) — say a number, 'zoom N', 'what is N', or 'back'.",
                    }
                if wants_zoom and ("click" not in text):
                    sub_count = self.label_overlay.drill_into_target(target, sw, sh)
                    return {
                        "status": "cursor",
                        "message": f"Zoomed into '{target.name}' ({sub_count} sub-zones) — say a number or 'click N'.",
                    }

                move_mouse_to_screen(cx, cy)
                if "right click" in text:
                    mouse_click("right")
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Right-clicked {target.name}."}
                if "double click" in text:
                    mouse_double_click()
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Double-clicked {target.name}."}
                if "move" in text or "hover" in text or "point" in text:
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Moved cursor to {target.name}."}
                mouse_click("left")
                self.label_overlay.clear_labels()
                return {"status": "cursor", "message": f"Clicked {target.name}."}

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

        # 4. Voice-Triggered Keyboard Navigation
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

        # 5. Direct single-step cursor / click / scroll controls
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
        self.label_overlay.clear_labels()
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
