import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, List


EDITOR_WEB_KNOWLEDGE: Dict[str, Dict[str, str]] = {
    "media": {
        "title": "Media / Import",
        "purpose": "Import video clips, images, and audio files into the project bin and drag them onto the timeline.",
    },
    "import": {
        "title": "Import Media",
        "purpose": "Opens file selection to bring source footage, audio, or graphics into the editor.",
    },
    "record": {
        "title": "Record & Create",
        "purpose": "Record screen, webcam, or voiceover directly into the editing project.",
    },
    "library": {
        "title": "Content Library",
        "purpose": "Browse stock video, stock audio, stickers, overlays, and backgrounds.",
    },
    "templates": {
        "title": "Templates",
        "purpose": "Start from pre-built video layouts, text styles, or social aspect-ratio presets.",
    },
    "text": {
        "title": "Text & Titles",
        "purpose": "Add titles, animated text blocks, lower thirds, or callouts over clips.",
    },
    "transitions": {
        "title": "Transitions",
        "purpose": "Insert cuts, dissolves, wipes, or motion transitions between clips or at clip edges.",
    },
    "captions": {
        "title": "Captions / Subtitles",
        "purpose": "Generate, edit, or style captions/subtitles for spoken dialogue.",
    },
    "audio": {
        "title": "Audio & Volume",
        "purpose": "Adjust clip volume, mute audio, detach audio, or apply audio fade-in/fade-out.",
    },
    "fade": {
        "title": "Fade",
        "purpose": "Smoothly fade clip visuals or audio in at the start and out at the end.",
    },
    "filters": {
        "title": "Filters",
        "purpose": "Apply stylized color looks or mood presets to selected video clips.",
    },
    "effects": {
        "title": "Effects",
        "purpose": "Add visual effects such as blur, zoom/motion, glitch, or glow to clips.",
    },
    "adjust": {
        "title": "Adjust Colors",
        "purpose": "Fine-tune exposure, contrast, saturation, temperature, and tint.",
    },
    "speed": {
        "title": "Speed & Duration",
        "purpose": "Change playback speed (slow motion or time-lapse) and adjust clip duration.",
    },
    "timeline": {
        "title": "Timeline",
        "purpose": "Arrange clips across tracks, scrub the playhead, split/trim clips, and zoom time.",
    },
    "export": {
        "title": "Export / Share",
        "purpose": "Choose resolution/quality and render/export the finished video file.",
    },
}


def enrich_with_web_knowledge(name: str) -> Dict[str, str]:
    low = (name or "").lower().strip()
    for key, info in EDITOR_WEB_KNOWLEDGE.items():
        if key in low or info["title"].lower() in low:
            return {
                "matched_topic": info["title"],
                "purpose": info["purpose"],
            }
    return {
        "matched_topic": name or "Editor Control",
        "purpose": (
            f"Interactive control '{name}' in the active video editor."
            if name
            else "Interactive control in the active video editor."
        ),
    }


def _get_foreground_info() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "window_title": "",
        "process_name": "",
        "rect": {"left": 0, "top": 0, "right": 1920, "bottom": 1080},
    }
    if not sys.platform.startswith("win"):
        return info

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return info

    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        info["window_title"] = buf.value

    r = wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(r)):
        info["rect"] = {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom}

    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if hproc:
            try:
                pbuf = ctypes.create_unicode_buffer(260)
                size = wintypes.DWORD(260)
                if kernel32.QueryFullProcessImageNameW(hproc, 0, pbuf, ctypes.byref(size)):
                    info["process_name"] = Path(pbuf.value).name
            finally:
                kernel32.CloseHandle(hproc)

    return info


def _scan_uia_elements(max_items: int = 80) -> List[Dict[str, Any]]:
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return []

    found: List[Dict[str, Any]] = []
    try:
        with auto.UIAutomationInitializerInThread():
            fg = auto.GetForegroundControl()
            if fg is None:
                return []

            interactive_types = {
                auto.ControlType.ButtonControl,
                auto.ControlType.CheckBoxControl,
                auto.ControlType.RadioButtonControl,
                auto.ControlType.ComboBoxControl,
                auto.ControlType.TabItemControl,
                auto.ControlType.MenuItemControl,
                auto.ControlType.SliderControl,
                auto.ControlType.HyperlinkControl,
                auto.ControlType.ListItemControl,
                auto.ControlType.TreeItemControl,
            }

            walker = auto.ControlViewWalker
            stack = [fg]
            visited = 0

            while stack and len(found) < max_items and visited < 1800:
                ctrl = stack.pop()
                visited += 1
                try:
                    if ctrl.IsOffscreen or not ctrl.IsEnabled:
                        continue
                    rect = ctrl.BoundingRectangle
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w < 10 or h < 10:
                        continue
                    if ctrl.ControlType in interactive_types:
                        name = (ctrl.Name or "").strip()
                        ctype = getattr(ctrl.ControlTypeName, "strip", lambda: str(ctrl.ControlType))()
                        mapped = enrich_with_web_knowledge(name)
                        found.append(
                            {
                                "name": name,
                                "control_type": ctype,
                                "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                                "matched_topic": mapped["matched_topic"],
                                "purpose": mapped["purpose"],
                            }
                        )

                    children = []
                    child = walker.GetFirstChildControl(ctrl)
                    while child is not None:
                        children.append(child)
                        child = walker.GetNextSiblingControl(child)
                    for ch in reversed(children):
                        stack.append(ch)
                except Exception:
                    continue
    except Exception:
        return []

    return found


def scan_active_tool_and_map(output_path: Path) -> Dict[str, Any]:
    """Scan the currently active editor tool, its exposed controls/tabs, and enrich with editor knowledge."""
    fg_info = _get_foreground_info()
    uia_controls = _scan_uia_elements()

    title_low = (fg_info.get("window_title") or "").lower()
    proc_low = (fg_info.get("process_name") or "").lower()
    if "clipchamp" in title_low or "clipchamp" in proc_low:
        detected_tool = "Clipchamp"
    elif "capcut" in title_low or "capcut" in proc_low:
        detected_tool = "CapCut"
    elif "photoshop" in title_low or "photoshop" in proc_low:
        detected_tool = "Photoshop"
    elif "premiere" in title_low or "premiere" in proc_low:
        detected_tool = "Premiere Pro"
    else:
        detected_tool = fg_info.get("window_title") or fg_info.get("process_name") or "Active Editor"

    tabs_and_tools: List[Dict[str, Any]] = []
    for item in uia_controls:
        if item.get("name"):
            tabs_and_tools.append(item)

    if not tabs_and_tools:
        for key, info in EDITOR_WEB_KNOWLEDGE.items():
            tabs_and_tools.append(
                {
                    "name": info["title"],
                    "control_type": "ReferenceTool",
                    "rect": None,
                    "matched_topic": info["title"],
                    "purpose": info["purpose"],
                    "key": key,
                }
            )

    payload: Dict[str, Any] = {
        "detected_tool": detected_tool,
        "window_title": fg_info.get("window_title", ""),
        "process_name": fg_info.get("process_name", ""),
        "rect": fg_info.get("rect", {}),
        "uia_control_count": len(uia_controls),
        "controls": uia_controls,
        "knowledge_map": tabs_and_tools,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
