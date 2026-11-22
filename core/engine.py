import json
import re
from pathlib import Path
from typing import Dict, Any, Tuple


def normalize_phrase(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s']", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


class CommandEngine:
    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir)
        self.settings_path = self.root_dir / "config" / "settings.json"
        self.settings = self._load_json(self.settings_path)
        self.horror_active = False
        self.profiles = self._load_profiles()
        self.theme, self.prompts = self.load_theme(self.settings.get("active_theme", "re_leon"))

    def _load_json(self, path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def save_settings(self) -> None:
        with self.settings_path.open("w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=2)

    def load_theme(self, theme_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        theme_dir = self.root_dir / "themes" / theme_id
        theme = self._load_json(theme_dir / "theme.json")
        prompts = self._load_json(theme_dir / "prompts.json")
        self.settings["active_theme"] = theme_id
        self.horror_active = False
        return theme, prompts

    def _load_profiles(self) -> Dict[str, Dict[str, Any]]:
        profiles = {}
        for p in sorted((self.root_dir / "config" / "profiles").glob("*.json")):
            data = self._load_json(p)
            profiles[p.stem] = data
        return profiles

    def prompt(self, key: str, **kwargs) -> str:
        state_key = "horror" if self.horror_active else "normal"
        pool = self.prompts.get(state_key, self.prompts.get("normal", {}))
        template = pool.get(key, self.prompts.get("normal", {}).get(key, key))
        ctx = {
            "mode": self.settings.get("compute_mode", "cpu").upper(),
            "app": self.settings.get("active_app", "auto").title(),
            "voice_mode": self.settings.get("voice_mode", "always_on"),
            **kwargs,
        }
        return template.format(**ctx)

    def check_mode_phrase(self, utterance: str) -> Tuple[bool, str]:
        norm = normalize_phrase(utterance)
        horror_cfg = self.theme.get("plushie", {}).get("horror_mode", {})
        triggers = [normalize_phrase(t) for t in horror_cfg.get("triggers", [])]
        reverts = [normalize_phrase(r) for r in horror_cfg.get("revert_phrases", [])]

        if not self.horror_active and any(t and t in norm for t in triggers):
            self.horror_active = True
            return True, self.prompt("horror_enter")

        if self.horror_active and any(r and r in norm for r in reverts):
            self.horror_active = False
            return True, self.prompt("horror_exit")

        return False, ""

    def resolve_command(self, utterance: str, app_key: str = "capcut", window_ok: bool = True, text_input_focused: bool = False) -> Dict[str, Any]:
        switched, mode_msg = self.check_mode_phrase(utterance)
        if switched:
            return {"status": "mode_changed", "horror_active": self.horror_active, "message": mode_msg}

        norm = normalize_phrase(utterance)
        profile = self.profiles.get(app_key)
        app_label = profile["app_name"] if profile else app_key.title()

        if not profile:
            return {
                "status": "cant_do",
                "reason_code": "unsupported_app",
                "message": self.prompt("cant_do_unsupported", action=utterance, app=app_label),
            }

        matched_name = None
        matched_cmd = None
        for cmd_name, cmd_cfg in profile.get("commands", {}).items():
            aliases = [normalize_phrase(a) for a in cmd_cfg.get("aliases", [])]
            if norm in aliases or any(a and f" {a} " in f" {norm} " for a in aliases):
                matched_name = cmd_name
                matched_cmd = cmd_cfg
                break

        if not matched_cmd:
            return {
                "status": "cant_do",
                "reason_code": "unmapped",
                "message": self.prompt("cant_do_unmapped", action=utterance, app=app_label),
            }

        if not matched_cmd.get("supported", True):
            detail = matched_cmd.get("reason") or "not supported in current setup"
            return {
                "status": "cant_do",
                "reason_code": "unsupported",
                "message": f"{self.prompt('cant_do_unsupported', action=matched_name, app=app_label)} ({detail})",
            }

        keys = matched_cmd.get("keys", [])
        if not window_ok or text_input_focused:
            return {
                "status": "cant_do",
                "reason_code": "focus",
                "message": self.prompt("cant_do_focus", action=matched_name, keys="+".join(keys), app=app_label),
            }

        return {
            "status": "execute",
            "command": matched_name,
            "keys": keys,
            "requires_confirm": bool(matched_cmd.get("requires_confirm", False)),
            "message": self.prompt("executed", action=matched_name, keys="+".join(keys), app=app_label),
        }
