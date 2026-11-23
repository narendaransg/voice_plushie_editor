import argparse
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QMessageBox, QHBoxLayout, QComboBox

from core.editor_profiles import (
    build_knowledge_map,
    detect_editor_key,
    load_profiles_from_dir,
    match_editor_macro,
)
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
    """Connects overlay, dynamic editor profiles, bidirectional levels, hover-first mover, drag/timeline edits, and voice."""

    def __init__(self, root_dir: Path, enable_voice: bool = True):
        self.root_dir = Path(root_dir)
        self.enable_voice = enable_voice
        self.scan_file = self.root_dir / "ui" / "active_tool_map.json"
        self.profiles_dir = self.root_dir / "config" / "profiles"
        self.editor_profiles: Dict[str, Dict[str, Any]] = load_profiles_from_dir(self.profiles_dir)
        self.active_editor_key: str = "clipchamp"
        self.active_knowledge_map: Dict[str, str] = build_knowledge_map(None)
        self.tool_map: Dict[str, Any] = {}

        self.overlay = PlushieOverlayWindow(self.root_dir)
        self.label_overlay = InteractiveLabelOverlay(scan_file=self.scan_file)
        self.label_overlay.set_knowledge_map(self.active_knowledge_map)

        self._cont_dir: Optional[Tuple[int, int]] = None
        self._cont_scroll: int = 0
        self._cont_speed: int = 6
        self._cont_timer = QTimer()
        self._cont_timer.setInterval(30)
        self._cont_timer.timeout.connect(self._on_continuous_tick)

        self._add_extra_controls()

        self._pending_confirm: Optional[dict] = None
        self.overlay.handle_utterance = self.on_utterance  # type: ignore[method-assign]

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

    def _sync_active_editor_profile(self) -> Dict[str, Any]:
        self.editor_profiles = load_profiles_from_dir(self.profiles_dir)
        title = str(self.tool_map.get("window_title") or "")
        proc = str(self.tool_map.get("process_name") or "")
        detected = str(self.tool_map.get("detected_tool") or "")
        combined_title = f"{title} {detected}".strip()

        key = detect_editor_key(combined_title, proc, self.editor_profiles)
        self.active_editor_key = key
        profile = self.editor_profiles.get(key, {})

        if hasattr(self.overlay, "engine") and isinstance(getattr(self.overlay.engine, "settings", None), dict):
            self.overlay.engine.settings["active_app"] = key

        self.active_knowledge_map = build_knowledge_map(profile)
        self.label_overlay.set_knowledge_map(self.active_knowledge_map)
        return profile

    def run_tool_scan(self, announce: bool = False) -> Dict[str, Any]:
        self.tool_map = scan_active_tool_and_map(self.scan_file)
        profile = self._sync_active_editor_profile()
        tool_name = profile.get("app_name") or self.tool_map.get("detected_tool") or "Active Editor"
        ctrl_count = self.tool_map.get("uia_control_count", 0)
        if announce:
            self.overlay.status_label.setText(
                f"Active editor: '{tool_name}' ({ctrl_count} UIA controls, dynamic UI map ready)."
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
            self._sync_active_editor_profile()
            sw, sh = get_screen_size()
            count = self.label_overlay.show_sectors(sw, sh, exclude_rect=self.overlay.geometry())
            profile = self.editor_profiles.get(self.active_editor_key, {})
            tool_name = profile.get("app_name") or self.tool_map.get("detected_tool") or "Editor"
            self.overlay.status_label.setText(
                f"{tool_name}: {count} sectors — say '2' to hover/drill, 'go up'/'back', or 'hide'."
            )

    def _on_continuous_tick(self) -> None:
        if self._cont_dir is not None:
            dx, dy = self._cont_dir
            move_mouse_relative(dx * self._cont_speed, dy * self._cont_speed)
        if self._cont_scroll != 0:
            step_units = self._cont_scroll * max(1, self._cont_speed // 4)
            mouse_scroll(step_units)

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

    def _extract_two_numbers(self, text: str) -> Optional[Tuple[int, int]]:
        nums: List[int] = []
        for m in re.finditer(r"\b(\d{1,2})\b", text):
            nums.append(int(m.group(1)))
        if len(nums) < 2:
            cleaned = re.sub(r"[^a-z\s]", " ", text)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            for phrase, val in sorted(WORD_NUMBERS.items(), key=lambda kv: -len(kv[0])):
                if re.search(rf"\b{re.escape(phrase)}\b", cleaned) and val not in nums:
                    nums.append(val)
        if len(nums) >= 2:
            return nums[0], nums[1]
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
        self._sync_active_editor_profile()
        self.overlay.status_label.setText("Command packs & editor profiles reloaded.")

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

    def _lookup_purpose(self, query_text: str) -> Optional[str]:
        low = query_text.lower().strip()
        for key, desc in self.active_knowledge_map.items():
            if key and re.search(rf"\b{re.escape(key)}\b", low):
                return f"{key.replace('_', ' ').title()}: {desc}"
        mapped = enrich_with_web_knowledge(low)
        if mapped.get("matched_topic") and mapped["matched_topic"].lower() != low:
            return f"{mapped['matched_topic']}: {mapped['purpose']}"
        return None

    def _perform_drag(self, start_xy: Optional[Tuple[int, int]], end_xy: Tuple[int, int], label: str) -> str:
        if start_xy is not None:
            move_mouse_to_screen(*start_xy)
            time.sleep(0.04)
        mouse_down("left")
        time.sleep(0.05)
        move_mouse_to_screen(*end_xy)
        time.sleep(0.05)
        mouse_up("left")
        self.label_overlay.clear_labels()
        return f"Dragged {label}."

    def _handle_cursor_utterance(self, utterance: str) -> Optional[dict]:
        text = re.sub(r"\s+", " ", utterance.lower()).strip()
        fine_step = 35 if any(w in text for w in ("tiny", "fine", "little", "bit", "slow")) else 85
        if any(w in text for w in ("far", "big", "lot", "fast")):
            fine_step = 180

        # 0. Rescan active tool & profile
        if any(p in text for p in ("rescan", "scan app", "scan tool", "refresh map", "detect editor")):
            info = self.run_tool_scan(announce=False)
            profile = self.editor_profiles.get(self.active_editor_key, {})
            tool_name = profile.get("app_name") or info.get("detected_tool", "Editor")
            return {
                "status": "cursor",
                "message": f"Detected '{tool_name}' ({info.get('uia_control_count', 0)} UIA controls).",
            }

        # 1. Stop continuous movement / scroll
        if text in ("stop", "halt", "freeze", "stop moving", "stop scrolling"):
            was_moving = self._cont_dir is not None or self._cont_scroll != 0
            self._stop_continuous()
            return {
                "status": "cursor",
                "message": "Stopped continuous motion." if was_moving else "Motion already stopped.",
            }

        # 2. Show / Hide / Step Up & Down Levels (sectors <-> zones <-> groups)
        if any(p in text for p in ("show labels", "show sectors", "label controls", "show buttons", "sectors")):
            self._sync_active_editor_profile()
            sw, sh = get_screen_size()
            count = self.label_overlay.show_sectors(sw, sh, exclude_rect=self.overlay.geometry())
            return {
                "status": "cursor",
                "message": f"Level 'sectors' ({count}) — say a number to hover/drill, 'go up'/'back', or 'hide'.",
            }

        if any(p in text for p in ("hide labels", "close labels", "hide targets", "clear labels", "hide sectors", "hide", "cancel labels")):
            self._stop_continuous()
            self.label_overlay.clear_labels()
            return {"status": "cursor", "message": "Overlay hidden."}

        if any(p in text for p in ("go up", "level up", "back sector", "go back", "previous level", "back")) and self.label_overlay.isVisible():
            prev = self.label_overlay.go_back_level()
            if prev:
                return {"status": "cursor", "message": f"Moved up to level '{prev}'."}
            return {"status": "cursor", "message": "Exited overlay."}

        # Drag target A to target B ("drag 2 to 6") or drag current/target to timeline
        if "drag" in text and "to" in text and self.label_overlay.isVisible():
            pair = self._extract_two_numbers(text)
            if pair is not None:
                src = self.label_overlay.get_target_by_number(pair[0])
                dst = self.label_overlay.get_target_by_number(pair[1])
                if src is not None and dst is not None:
                    msg = self._perform_drag(src.center, dst.center, f"#{src.index} {src.name} -> #{dst.index} {dst.name}")
                    return {"status": "cursor", "message": msg}

        if "drag" in text and "timeline" in text:
            sw, sh = get_screen_size()
            trect = self.label_overlay.get_timeline_rect(sw, sh)
            num = self._extract_target_number(text) if self.label_overlay.isVisible() else None
            src = self.label_overlay.get_target_by_number(num) if num is not None else None
            start_xy = src.center if src is not None else None
            end_xy = (trect.center().x(), trect.center().y())
            msg = self._perform_drag(start_xy, end_xy, "selection to timeline")
            return {"status": "cursor", "message": msg}

        # Contextual help: what is X / what does X do
        if any(q in text for q in ("what is", "what does", "describe", "purpose", "use of")):
            if self.label_overlay.isVisible():
                num = self._extract_target_number(text)
                target = (
                    self.label_overlay.get_target_by_number(num)
                    if num is not None
                    else self.label_overlay.get_target_by_name(text)
                )
                if target is not None:
                    move_mouse_to_screen(*target.center)
                    return {"status": "cursor", "message": f"#{target.index} {target.name}: {target.purpose}"}
            help_msg = self._lookup_purpose(text)
            if help_msg:
                return {"status": "cursor", "message": help_msg}

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

                # Explicit click commands
                if "right click" in text:
                    move_mouse_to_screen(cx, cy)
                    mouse_click("right")
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Right-clicked {target.name}."}
                if "double click" in text:
                    move_mouse_to_screen(cx, cy)
                    mouse_double_click()
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Double-clicked {target.name}."}
                if "click" in text or "tap" in text:
                    move_mouse_to_screen(cx, cy)
                    mouse_click("left")
                    self.label_overlay.clear_labels()
                    return {"status": "cursor", "message": f"Clicked {target.name}."}

                # Hover first + drill down a level when picking a number or saying 'go down'/'drill down'/'zoom'/'go to'
                move_mouse_to_screen(cx, cy)
                wants_drill = any(w in text for w in ("go down", "drill down", "zoom", "deeper", "go to", "open", "inside"))
                if num is not None or wants_drill:
                    sub_count = self.label_overlay.drill_into_target(target, sw, sh)
                    lvl = self.label_overlay.level_name
                    return {
                        "status": "cursor",
                        "message": f"Hovering #{target.index} {target.name} -> level '{lvl}' ({sub_count}) — say a number, 'go up', or 'click'.",
                    }

                return {
                    "status": "cursor",
                    "message": f"Hovering #{target.index} {target.name} — say 'click', 'go down', 'go up', or 'hide'.",
                }

            # Drill down current level even without a specific target number
            if any(w in text for w in ("go down", "drill down", "deeper")) and self.label_overlay._targets:
                sw, sh = get_screen_size()
                first = self.label_overlay._targets[0]
                move_mouse_to_screen(*first.center)
                sub_count = self.label_overlay.drill_into_target(first, sw, sh)
                return {
                    "status": "cursor",
                    "message": f"Drilled to level '{self.label_overlay.level_name}' ({sub_count}) — say 'go up' to return.",
                }

        # 3. Timeline hover left / right & fine horizontal nudging
        if any(p in text for p in ("hover left", "nudge left", "scrub left")):
            ok, detail = move_mouse_relative(-fine_step, 0)
            return {"status": "cursor", "message": f"Timeline hover left ({fine_step}px): {detail}" if ok else detail}
        if any(p in text for p in ("hover right", "nudge right", "scrub right")):
            ok, detail = move_mouse_relative(fine_step, 0)
            return {"status": "cursor", "message": f"Timeline hover right ({fine_step}px): {detail}" if ok else detail}

        # 4. Continuous Directional Hold & Relative Wheel Modes
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
                return {"status": "cursor", "message": "Continuous cursor glide started — say 'stop' to halt."}

        if any(p in text for p in ("keep scrolling", "start scrolling", "auto scroll")):
            if "up" in text:
                self._cont_scroll = 20
                self._cont_timer.start()
                return {"status": "cursor", "message": "Continuous scroll up — say 'stop' to halt."}
            if "down" in text:
                self._cont_scroll = -20
                self._cont_timer.start()
                return {"status": "cursor", "message": "Continuous scroll down — say 'stop' to halt."}

        if text in ("faster", "move faster", "speed up"):
            self._cont_speed = min(20, self._cont_speed + 3)
            return {"status": "cursor", "message": f"Motion speed set to {self._cont_speed}."}
        if text in ("slower", "move slower", "slow down"):
            self._cont_speed = max(2, self._cont_speed - 2)
            return {"status": "cursor", "message": f"Motion speed set to {self._cont_speed}."}

        # 5. High-frequency editing macros from active profile
        active_profile = self.editor_profiles.get(self.active_editor_key)
        macro = match_editor_macro(text, active_profile)
        if macro is not None:
            label, keys = macro
            ok, detail = send_key_combo(keys)
            return {"status": "cursor", "message": f"{label}: {detail}" if ok else detail}

        # 6. Voice-Triggered Keyboard Navigation
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

        # 7. Direct single-step cursor / click / drag / scroll controls
        if "double click" in text:
            ok, detail = mouse_double_click()
            return {"status": "cursor", "message": detail if ok else detail}
        if "right click" in text:
            ok, detail = mouse_click("right")
            return {"status": "cursor", "message": detail if ok else detail}
        if any(k in text for k in ("start drag", "hold click", "mouse down", "drag start")):
            ok, detail = mouse_down("left")
            return {"status": "cursor", "message": detail if ok else detail}
        if any(k in text for k in ("drop", "release", "mouse up", "drag end", "let go")):
            ok, detail = mouse_up("left")
            return {"status": "cursor", "message": detail if ok else detail}
        if text in ("click", "left click", "tap"):
            ok, detail = mouse_click("left")
            return {"status": "cursor", "message": detail if ok else detail}

        if "scroll up" in text:
            ok, detail = mouse_scroll(240 if "fast" in text else 120)
            return {"status": "cursor", "message": detail if ok else detail}
        if "scroll down" in text:
            ok, detail = mouse_scroll(-240 if "fast" in text else -120)
            return {"status": "cursor", "message": detail if ok else detail}

        if "move left" in text or "go left" in text:
            ok, detail = move_mouse_relative(-fine_step, 0)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move right" in text or "go right" in text:
            ok, detail = move_mouse_relative(fine_step, 0)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move up" in text or "go up" in text:
            ok, detail = move_mouse_relative(0, -fine_step)
            return {"status": "cursor", "message": detail if ok else detail}
        if "move down" in text or "go down" in text:
            ok, detail = move_mouse_relative(0, fine_step)
            return {"status": "cursor", "message": detail if ok else detail}

        return None

    def on_utterance(self, utterance: str, window_ok: Optional[bool] = None, text_input_focused: bool = False) -> dict:
        cursor_res = self._handle_cursor_utterance(utterance)
        if cursor_res is not None:
            self.overlay._apply_theme_and_modes()
            self.overlay.status_label.setText(cursor_res.get("message", ""))
            return cursor_res

        engine = self.overlay.engine
        app_key = self.active_editor_key or engine.settings.get("active_app", "clipchamp")
        profile = self.editor_profiles.get(app_key) or engine.profiles.get(app_key, {})

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
