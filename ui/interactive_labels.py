import ctypes
import json
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


VIDEO_EDITOR_UI_MAP: Dict[str, Dict[str, str]] = {
    "header": {
        "title": "Header & Export Bar",
        "purpose": "Project title, undo/redo, settings, and Share/Export rendering options.",
    },
    "left_rail": {
        "title": "Left Tool Rail",
        "purpose": "Switch between Media, Record & Create, Content Library, Templates, Text, and Transitions.",
    },
    "left_drawer": {
        "title": "Asset & Media Drawer",
        "purpose": "Import video/audio clips, browse templates/text presets, and drag items onto the timeline.",
    },
    "preview_transport": {
        "title": "Preview Monitor & Play Controls",
        "purpose": "Inspect the video frame, play/pause playback, step frames, and scrub the playhead.",
    },
    "right_inspector": {
        "title": "Right Property Inspector",
        "purpose": "Edit selected clip properties: Captions, Audio volume/fade, Filters, Effects, Color, Speed.",
    },
    "timeline": {
        "title": "Timeline & Multi-Track Editor",
        "purpose": "Arrange, trim, split, and layer video and audio clips along time, with timeline zoom on the bottom right.",
    },
    "import_media": {
        "title": "Import Media Button",
        "purpose": "Opens file picker to bring video clips, images, or audio files into your project.",
    },
    "text_tool": {
        "title": "Text Tab",
        "purpose": "Adds titles, captions, or lower-third text overlays to your video.",
    },
    "transitions_tool": {
        "title": "Transitions Tab",
        "purpose": "Adds crossfades, wipes, or motion transitions between timeline clips.",
    },
    "play_button": {
        "title": "Play / Pause Button",
        "purpose": "Starts or pauses real-time preview playback at the current playhead position.",
    },
    "captions_panel": {
        "title": "Captions Inspector",
        "purpose": "Generates or edits subtitles/captions for speech in the video.",
    },
    "audio_panel": {
        "title": "Audio Inspector",
        "purpose": "Adjusts clip loudness, mute state, or audio fade-in/fade-out.",
    },
    "filters_effects": {
        "title": "Filters & Effects Inspector",
        "purpose": "Applies visual color filters, blur/glitch effects, or color adjustments to clips.",
    },
    "speed_panel": {
        "title": "Speed Inspector",
        "purpose": "Changes playback speed (slow motion or speed-up) and clip duration.",
    },
    "export_button": {
        "title": "Export / Share Button",
        "purpose": "Renders and exports the final edited video file.",
    },
}


@dataclass
class InteractiveTarget:
    index: int
    name: str
    rect: QRect
    purpose: str
    kind: str = "control"  # "sector", "control", "subzone"

    @property
    def center(self) -> Tuple[int, int]:
        return self.rect.center().x(), self.rect.center().y()


def _get_foreground_window_rect(screen_w: int, screen_h: int) -> QRect:
    if hasattr(ctypes, "windll"):
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                left = max(0, r.left)
                top = max(0, r.top)
                right = min(screen_w, r.right)
                bottom = min(screen_h, r.bottom)
                if right - left > 120 and bottom - top > 120:
                    return QRect(left, top, right - left, bottom - top)
    return QRect(0, 0, screen_w, screen_h)


def _match_editor_purpose(label: str, fallback_key: str) -> str:
    low = (label or "").lower()
    for _, info in VIDEO_EDITOR_UI_MAP.items():
        if info["title"].lower() in low:
            return info["purpose"]
    if "export" in low or "share" in low:
        return VIDEO_EDITOR_UI_MAP["export_button"]["purpose"]
    if "import" in low or "media" in low:
        return VIDEO_EDITOR_UI_MAP["import_media"]["purpose"]
    if "text" in low:
        return VIDEO_EDITOR_UI_MAP["text_tool"]["purpose"]
    if "transition" in low:
        return VIDEO_EDITOR_UI_MAP["transitions_tool"]["purpose"]
    if "play" in low:
        return VIDEO_EDITOR_UI_MAP["play_button"]["purpose"]
    if "caption" in low:
        return VIDEO_EDITOR_UI_MAP["captions_panel"]["purpose"]
    if "audio" in low:
        return VIDEO_EDITOR_UI_MAP["audio_panel"]["purpose"]
    if "filter" in low or "effect" in low or "color" in low:
        return VIDEO_EDITOR_UI_MAP["filters_effects"]["purpose"]
    if "speed" in low:
        return VIDEO_EDITOR_UI_MAP["speed_panel"]["purpose"]
    return VIDEO_EDITOR_UI_MAP.get(fallback_key, {}).get(
        "purpose",
        f"Interactive control '{label}' inside the active video editor." if label else "Interactive control in the active video editor.",
    )


def _build_major_sectors(win: QRect) -> List[InteractiveTarget]:
    wx, wy, ww, wh = win.left(), win.top(), win.width(), win.height()
    sectors_spec = [
        ("Header & Export", QRect(wx + int(ww * 0.06), wy + 4, int(ww * 0.90), 44), "header"),
        ("Left Tool Rail", QRect(wx + 2, wy + int(wh * 0.08), 62, int(wh * 0.62)), "left_rail"),
        ("Media Drawer", QRect(wx + int(ww * 0.06), wy + int(wh * 0.08), int(ww * 0.22), int(wh * 0.62)), "left_drawer"),
        ("Preview & Play", QRect(wx + int(ww * 0.29), wy + int(wh * 0.08), int(ww * 0.62), int(wh * 0.60)), "preview_transport"),
        ("Right Inspector", QRect(wx + ww - 68, wy + int(wh * 0.08), 66, int(wh * 0.66)), "right_inspector"),
        ("Timeline & Tracks", QRect(wx + int(ww * 0.06), wy + int(wh * 0.70), int(ww * 0.92), int(wh * 0.28)), "timeline"),
    ]
    return [
        InteractiveTarget(
            index=i,
            name=title,
            rect=rect,
            purpose=VIDEO_EDITOR_UI_MAP[key]["purpose"],
            kind="sector",
        )
        for i, (title, rect, key) in enumerate(sectors_spec, start=1)
    ]


def _load_scanned_controls_in_rect(scan_file: Optional[Path], region: QRect, screen_w: int, screen_h: int, max_items: int = 18) -> List[InteractiveTarget]:
    if scan_file is None or not scan_file.exists():
        return []
    try:
        data: Dict[str, Any] = json.loads(scan_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    raw_controls = data.get("controls") or []
    targets: List[InteractiveTarget] = []
    for item in raw_controls:
        if len(targets) >= max_items:
            break
        r = item.get("rect") or {}
        left = int(r.get("left", 0))
        top = int(r.get("top", 0))
        right = int(r.get("right", 0))
        bottom = int(r.get("bottom", 0))
        w = right - left
        h = bottom - top
        if w < 12 or h < 12 or w > screen_w * 0.9 or h > screen_h * 0.9:
            continue
        qrect = QRect(left, top, w, h)
        if not region.intersects(qrect):
            continue
        if any(
            abs(t.rect.left() - qrect.left()) < 10
            and abs(t.rect.top() - qrect.top()) < 10
            and abs(t.rect.width() - qrect.width()) < 10
            and abs(t.rect.height() - qrect.height()) < 10
            for t in targets
        ):
            continue
        name = (item.get("name") or "").strip() or f"Control {len(targets) + 1}"
        purpose = (item.get("purpose") or "").strip() or _match_editor_purpose(name, "preview_transport")
        targets.append(
            InteractiveTarget(
                index=len(targets) + 1,
                name=name,
                rect=qrect,
                purpose=purpose,
                kind="control",
            )
        )
    return targets


def _build_detailed_sector_targets(sector: InteractiveTarget) -> List[InteractiveTarget]:
    """Break a chosen sector into detailed sub-controls/slots for a clean sector view."""
    r = sector.rect
    x, y, w, h = r.left(), r.top(), r.width(), r.height()
    items: List[Tuple[str, QRect, str]] = []

    if sector.name == "Header & Export":
        items = [
            ("Project Menu", QRect(x, y, max(60, w // 4), h), VIDEO_EDITOR_UI_MAP["header"]["purpose"]),
            ("Undo / Redo", QRect(x + w // 4, y, max(60, w // 4), h), "Undo or redo recent timeline edits."),
            ("Workspace / Zoom", QRect(x + w // 2, y, max(60, w // 4), h), "Adjust view or account options."),
            ("Share / Export", QRect(x + (3 * w) // 4, y, max(60, w // 4), h), VIDEO_EDITOR_UI_MAP["export_button"]["purpose"]),
        ]
    elif sector.name == "Left Tool Rail":
        names_keys = [
            ("Media", "import_media"),
            ("Record", "left_rail"),
            ("Library", "left_rail"),
            ("Templates", "left_rail"),
            ("Text", "text_tool"),
            ("Transitions", "transitions_tool"),
        ]
        step_h = max(24, h // len(names_keys))
        for i, (nm, k) in enumerate(names_keys):
            items.append((nm, QRect(x, y + i * step_h, w, step_h - 2), VIDEO_EDITOR_UI_MAP[k]["purpose"]))
    elif sector.name == "Media Drawer":
        items = [
            ("Import Media", QRect(x + 8, y + 8, max(80, w - 16), 44), VIDEO_EDITOR_UI_MAP["import_media"]["purpose"]),
            ("Asset Library Grid", QRect(x + 8, y + 60, max(80, w - 16), max(60, h - 72)), VIDEO_EDITOR_UI_MAP["left_drawer"]["purpose"]),
        ]
    elif sector.name == "Preview & Play":
        play_h = max(36, int(h * 0.14))
        items = [
            ("Video Canvas", QRect(x + 8, y + 8, max(80, w - 16), max(60, h - play_h - 16)), VIDEO_EDITOR_UI_MAP["preview_transport"]["purpose"]),
            ("Play / Transport", QRect(x + int(w * 0.25), y + h - play_h, max(80, int(w * 0.50)), play_h), VIDEO_EDITOR_UI_MAP["play_button"]["purpose"]),
        ]
    elif sector.name == "Right Inspector":
        panels = [
            ("Captions", "captions_panel"),
            ("Audio", "audio_panel"),
            ("Fade", "audio_panel"),
            ("Filters", "filters_effects"),
            ("Effects", "filters_effects"),
            ("Color", "filters_effects"),
            ("Speed", "speed_panel"),
        ]
        step_h = max(24, h // len(panels))
        for i, (nm, k) in enumerate(panels):
            items.append((nm, QRect(x, y + i * step_h, w, step_h - 2), VIDEO_EDITOR_UI_MAP[k]["purpose"]))
    else:
        top_h = max(28, int(h * 0.25))
        mid_h = max(32, int(h * 0.42))
        bot_h = max(24, h - top_h - mid_h)
        items = [
            ("Time Ruler / Playhead", QRect(x + 8, y + 4, max(80, w - 16), top_h), "Scrub or position the timeline playhead."),
            ("Video Track", QRect(x + 8, y + top_h + 6, max(80, w - 16), mid_h), "Select, trim, or split video clips on the timeline."),
            ("Audio & Zoom Bar", QRect(x + 8, y + top_h + mid_h + 8, max(80, w - 16), bot_h), "Manage audio tracks and timeline zoom level."),
        ]

    return [
        InteractiveTarget(index=i, name=nm, rect=qrect, purpose=purp, kind="control")
        for i, (nm, qrect, purp) in enumerate(items, start=1)
    ]


def _subdivide_target_level(target: InteractiveTarget) -> List[InteractiveTarget]:
    """Subdivide a selected target into a 2x2 finer sub-level for deeper precision."""
    r = target.rect
    hw = max(16, r.width() // 2)
    hh = max(16, r.height() // 2)
    quads = [
        ("Top-Left", QRect(r.left(), r.top(), hw, hh)),
        ("Top-Right", QRect(r.left() + hw, r.top(), r.width() - hw, hh)),
        ("Bottom-Left", QRect(r.left(), r.top() + hh, hw, r.height() - hh)),
        ("Bottom-Right", QRect(r.left() + hw, r.top() + hh, r.width() - hw, r.height() - hh)),
    ]
    return [
        InteractiveTarget(
            index=i,
            name=f"{target.name} ({qname})",
            rect=qrect,
            purpose=f"{qname} sub-area of {target.name}: {target.purpose}",
            kind="subzone",
        )
        for i, (qname, qrect) in enumerate(quads, start=1)
    ]


class InteractiveLabelOverlay(QWidget):
    """Multi-level sector & control badge overlay backed by startup tool scan + knowledge map."""

    def __init__(self, scan_file: Optional[Path] = None):
        super().__init__(None)
        self.scan_file = scan_file
        self._targets: List[InteractiveTarget] = []
        self._history: List[Tuple[str, List[InteractiveTarget]]] = []
        self._level_name: str = "sectors"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    @property
    def level_name(self) -> str:
        return self._level_name

    def show_sectors(self, screen_w: int, screen_h: int) -> int:
        self._history.clear()
        win = _get_foreground_window_rect(screen_w, screen_h)
        self._targets = _build_major_sectors(win)
        self._level_name = "sectors"
        self.setGeometry(0, 0, screen_w, screen_h)
        if self._targets:
            self.show()
            self.raise_()
            self.update()
        return len(self._targets)

    def drill_into_target(self, target: InteractiveTarget, screen_w: int, screen_h: int) -> int:
        self._history.append((self._level_name, list(self._targets)))
        if target.kind == "sector":
            scanned_hits = _load_scanned_controls_in_rect(self.scan_file, target.rect, screen_w, screen_h, max_items=18)
            detail_targets = scanned_hits if len(scanned_hits) >= 2 else _build_detailed_sector_targets(target)
            self._targets = detail_targets
            self._level_name = f"sector:{target.name}"
        else:
            self._targets = _subdivide_target_level(target)
            self._level_name = f"zoom:{target.name}"

        self.setGeometry(0, 0, screen_w, screen_h)
        if self._targets:
            self.show()
            self.raise_()
            self.update()
        return len(self._targets)

    def go_back_level(self) -> Optional[str]:
        if not self._history:
            self.clear_labels()
            return None
        prev_level, prev_targets = self._history.pop()
        self._level_name = prev_level
        self._targets = prev_targets
        if self._targets:
            self.show()
            self.raise_()
            self.update()
        return self._level_name

    def clear_labels(self) -> None:
        self._history.clear()
        self._targets = []
        self._level_name = "sectors"
        self.hide()

    def get_target_by_number(self, num: int) -> Optional[InteractiveTarget]:
        for t in self._targets:
            if t.index == num:
                return t
        return None

    def get_target_by_name(self, spoken_text: str) -> Optional[InteractiveTarget]:
        cleaned = " ".join(spoken_text.lower().split())
        for t in self._targets:
            if t.name and len(t.name) >= 2 and t.name.lower() in cleaned:
                return t
        return None

    def paintEvent(self, event) -> None:
        _ = event
        if not self._targets:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

        for t in self._targets:
            is_sector = t.kind == "sector"
            border_color = QColor(80, 210, 255, 225) if is_sector else QColor(255, 204, 48, 225)
            painter.setPen(QPen(border_color, 2 if is_sector else 1))
            painter.drawRect(t.rect)

            tag = f"{t.index}" if not t.name else f"{t.index}:{t.name[:14]}"
            badge_w = max(26, min(145, len(tag) * 7 + 12))
            badge_h = 20
            bx = max(0, min(self.width() - badge_w, t.rect.left() + 2))
            by = max(0, min(self.height() - badge_h, t.rect.top() + 2))
            badge = QRect(bx, by, badge_w, badge_h)

            painter.fillRect(badge, QColor(16, 22, 34, 238))
            painter.setPen(QPen(border_color, 1))
            painter.drawRect(badge)
            painter.setPen(QPen(QColor(255, 255, 255, 255), 1))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
