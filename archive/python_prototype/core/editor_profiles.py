from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_UI_MAP: Dict[str, str] = {
    "header": "Top bar for project title, undo/redo, settings, and export/share options.",
    "left_rail": "Left tool rail for switching between media, text, transitions, effects, and templates.",
    "left_drawer": "Asset and media drawer for importing clips, browsing presets, and dragging items onto the timeline.",
    "preview_transport": "Preview monitor and playback controls for inspecting frames, scrubbing, and play/pause.",
    "right_inspector": "Property inspector for editing selected clip audio, captions, color, speed, effects, and keyframes.",
    "timeline": "Multi-track timeline for arranging, trimming, splitting, and zooming video and audio clips.",
    "import": "Imports video clips, audio tracks, images, or graphics into the project.",
    "text": "Adds titles, captions, subtitles, or text overlays to the video.",
    "transitions": "Applies cuts, fades, dissolves, or motion transitions between or onto clips.",
    "captions": "Generates, edits, or styles captions and subtitles for speech.",
    "audio": "Adjusts clip volume, mute state, fades, or detached audio tracks.",
    "speed": "Adjusts playback speed, slow motion, speed ramps, or clip duration.",
    "keyframe": "Marks keyframe points to animate position, scale, opacity, or effects over time.",
    "export": "Renders and exports the finished video file.",
}


def detect_editor_key(window_title: str, process_name: str, profiles: Dict[str, Dict[str, Any]]) -> str:
    haystack = f"{window_title or ''} {process_name or ''}".lower()
    for key, prof in profiles.items():
        keywords = [str(k).lower() for k in (prof.get("window_keywords") or []) if k]
        if any(kw in haystack for kw in keywords):
            return key
        if key.lower() in haystack:
            return key
    for fallback_key in ("clipchamp", "capcut"):
        if fallback_key in profiles:
            return fallback_key
    return next(iter(profiles.keys()), "clipchamp")


def build_knowledge_map(
    profile: Optional[Dict[str, Any]],
    fallback_map: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    merged: Dict[str, str] = dict(DEFAULT_UI_MAP)
    if fallback_map:
        for k, v in fallback_map.items():
            if isinstance(v, dict) and v.get("purpose"):
                merged[k.lower()] = str(v["purpose"])
            elif isinstance(v, str):
                merged[k.lower()] = v

    if profile:
        custom_map = profile.get("ui_map") or {}
        if isinstance(custom_map, dict):
            for k, v in custom_map.items():
                if isinstance(v, dict) and v.get("purpose"):
                    merged[k.lower()] = str(v["purpose"])
                elif isinstance(v, str):
                    merged[k.lower()] = v

        commands = profile.get("commands") or {}
        if isinstance(commands, dict):
            for cmd_name, cmd_cfg in commands.items():
                if not isinstance(cmd_cfg, dict):
                    continue
                reason = str(cmd_cfg.get("reason") or "").strip()
                if reason:
                    merged[cmd_name.replace("_", " ").lower()] = reason
                    for alias in cmd_cfg.get("aliases") or []:
                        al = str(alias).strip().lower()
                        if al and al not in merged:
                            merged[al] = f"{cmd_name.replace('_', ' ').title()} ({reason})"

    return merged


def match_editor_macro(text: str, profile: Optional[Dict[str, Any]]) -> Optional[Tuple[str, List[str]]]:
    if not profile:
        return None
    commands = profile.get("commands") or {}
    if not isinstance(commands, dict):
        return None
    cleaned = " ".join(text.lower().split())
    for cmd_name, cmd_cfg in commands.items():
        if not isinstance(cmd_cfg, dict):
            continue
        if cmd_cfg.get("supported") is False:
            continue
        keys = [str(k) for k in (cmd_cfg.get("keys") or []) if k]
        if not keys:
            continue
        aliases = [str(a).lower() for a in (cmd_cfg.get("aliases") or []) if a]
        if cleaned == cmd_name.replace("_", " ").lower() or cleaned in aliases:
            return (cmd_name.replace("_", " ").title(), keys)
    return None


def load_profiles_from_dir(profiles_dir: Path) -> Dict[str, Dict[str, Any]]:
    loaded: Dict[str, Dict[str, Any]] = {}
    if not profiles_dir.exists():
        return loaded
    for path in sorted(profiles_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                loaded[path.stem.lower()] = data
        except Exception:
            continue
    return loaded
