import ctypes
import json
import re
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ui.vision_grounder import VisionGrounder


VIDEO_EDITOR_UI_MAP: Dict[str, Dict[str, str]] = {
    "header": {
        "title": "Header & Export Bar",
        "purpose": "Project title, undo/redo, settings, and export/share options.",
    },
    "left_rail": {
        "title": "Left Tool Rail",
        "purpose": "Switch between media, text, transitions, effects, captions, and templates.",
    },
    "left_drawer": {
        "title": "Asset & Media Drawer",
        "purpose": "Import video/audio clips, browse presets, and drag items onto the timeline.",
    },
    "preview_transport": {
        "title": "Preview Monitor & Play Controls",
        "purpose": "Inspect the video frame, play/pause playback, step frames, and scrub the playhead.",
    },
    "right_inspector": {
        "title": "Right Inspector Rail",
        "purpose": "Access Captions, Audio, Fade, Filters, Effects, Adjust colors, Upscale, and Speed.",
    },
    "timeline": {
        "title": "Timeline & Multi-Track Editor",
        "purpose": "Arrange, trim, split, and layer video and audio clips along time.",
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


def _clamp_to_window(rect: QRect, bounds: QRect) -> QRect:
    clipped = rect.intersected(bounds)
    if clipped.isValid() and clipped.width() >= 12 and clipped.height() >= 12:
        return clipped
    x = max(bounds.left(), min(bounds.right() - 24, rect.left()))
    y = max(bounds.top(), min(bounds.bottom() - 24, rect.top()))
    w = max(12, min(bounds.right() - x, rect.width()))
    h = max(12, min(bounds.bottom() - y, rect.height()))
    return QRect(x, y, w, h)


def _match_editor_purpose(
    label: str,
    fallback_key: str,
    knowledge_map: Optional[Dict[str, str]] = None,
) -> str:
    low = (label or "").strip().lower()
    active_map: Dict[str, str] = {
        k: v["purpose"] for k, v in VIDEO_EDITOR_UI_MAP.items()
    }
    if knowledge_map:
        active_map.update({k.lower(): v for k, v in knowledge_map.items() if v})

    if low in active_map:
        return active_map[low]
    for key, desc in active_map.items():
        if key and re.search(rf"\b{re.escape(key)}\b", low):
            return desc
    if fallback_key in active_map:
        return active_map[fallback_key]
    return (
        f"Interactive control '{label}' inside the active video editor."
        if label
        else "Interactive control in the active video editor."
    )


def _fallback_sectors(win: QRect, knowledge_map: Optional[Dict[str, str]] = None) -> List[InteractiveTarget]:
    wx, wy, ww, wh = win.left(), win.top(), win.width(), win.height()
    sectors_spec = [
        ("Header & Export", QRect(wx + int(ww * 0.05), wy + 4, int(ww * 0.90), 42), "header"),
        ("Left Tool Rail", QRect(wx + 2, wy + int(wh * 0.07), 56, int(wh * 0.62)), "left_rail"),
        ("Media Drawer", QRect(wx + int(ww * 0.05), wy + int(wh * 0.07), int(ww * 0.19), int(wh * 0.62)), "left_drawer"),
        ("Preview & Play", QRect(wx + int(ww * 0.25), wy + int(wh * 0.07), int(ww * 0.68), int(wh * 0.60)), "preview_transport"),
        ("Right Inspector", QRect(wx + ww - 58, wy + int(wh * 0.07), 54, int(wh * 0.66)), "right_inspector"),
        ("Timeline & Tracks", QRect(wx + int(ww * 0.05), wy + int(wh * 0.69), int(ww * 0.90), int(wh * 0.28)), "timeline"),
    ]
    return [
        InteractiveTarget(
            index=i,
            name=title,
            rect=_clamp_to_window(rect, win),
            purpose=_match_editor_purpose(title, key, knowledge_map),
            kind="sector",
        )
        for i, (title, rect, key) in enumerate(sectors_spec, start=1)
    ]


def _load_scanned_controls_in_rect(
    scan_file: Optional[Path],
    region: QRect,
    bounds: QRect,
    screen_w: int,
    screen_h: int,
    knowledge_map: Optional[Dict[str, str]] = None,
    max_items: int = 18,
) -> List[InteractiveTarget]:
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
        qrect = _clamp_to_window(QRect(left, top, w, h), bounds)
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
        purpose = (item.get("purpose") or "").strip() or _match_editor_purpose(name, "preview_transport", knowledge_map)
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


class InteractiveLabelOverlay(QWidget):
    """Multi-level sector & control badge overlay using dynamic OpenCV segmentation + scoped grounding."""

    def __init__(self, scan_file: Optional[Path] = None):
        super().__init__(None)
        self.scan_file = scan_file
        self.grounder = VisionGrounder()
        self.knowledge_map: Dict[str, str] = {}
        self._targets: List[InteractiveTarget] = []
        self._history: List[Tuple[str, List[InteractiveTarget]]] = []
        self._level_name: str = "sectors"
        self._last_frame = None
        self._last_win_rect: Optional[QRect] = None

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

    def set_knowledge_map(self, knowledge_map: Dict[str, str]) -> None:
        self.knowledge_map = dict(knowledge_map or {})

    def _capture_clean_window(self, win: QRect, exclude_rect: Optional[QRect] = None):
        was_visible = self.isVisible()
        if was_visible:
            self.hide()
            app_inst = QApplication.instance()
            if app_inst is not None:
                app_inst.processEvents()
        try:
            excl_tuple = (
                (exclude_rect.left(), exclude_rect.top(), exclude_rect.width(), exclude_rect.height())
                if exclude_rect is not None and exclude_rect.isValid()
                else None
            )
            frame = self.grounder.capture_window_region(
                win.left(), win.top(), win.width(), win.height(), exclude_rect=excl_tuple
            )
        finally:
            if was_visible:
                self.show()
                self.raise_()
                self.update()
        return frame

    def show_sectors(self, screen_w: int, screen_h: int, exclude_rect: Optional[QRect] = None) -> int:
        self._history.clear()
        win = _get_foreground_window_rect(screen_w, screen_h)
        self._last_win_rect = win
        frame = self._capture_clean_window(win, exclude_rect=exclude_rect)
        self._last_frame = frame

        detected_targets: List[InteractiveTarget] = []
        if frame is not None:
            panels = self.grounder.detect_panels(frame, max_panels=8)
            for idx, p in enumerate(panels, start=1):
                px, py, pw, ph = p.bbox
                qrect = _clamp_to_window(QRect(win.left() + px, win.top() + py, pw, ph), win)
                detected_targets.append(
                    InteractiveTarget(
                        index=idx,
                        name=p.label,
                        rect=qrect,
                        purpose=_match_editor_purpose(p.label, "timeline", self.knowledge_map),
                        kind="sector",
                    )
                )

        self._targets = detected_targets if detected_targets else _fallback_sectors(win, self.knowledge_map)
        self._level_name = "sectors"
        self.setGeometry(0, 0, screen_w, screen_h)
        if self._targets:
            self.show()
            self.raise_()
            self.update()
        return len(self._targets)

    def drill_into_target(
        self,
        target: InteractiveTarget,
        screen_w: int,
        screen_h: int,
        force_subzone: bool = False,
    ) -> int:
        self._history.append((self._level_name, list(self._targets)))
        win = self._last_win_rect or _get_foreground_window_rect(screen_w, screen_h)

        if target.kind == "sector" and not force_subzone:
            frame = self._last_frame if self._last_frame is not None else self._capture_clean_window(win)
            detail_targets: List[InteractiveTarget] = []

            if frame is not None:
                rel_bbox = (
                    max(0, target.rect.left() - win.left()),
                    max(0, target.rect.top() - win.top()),
                    target.rect.width(),
                    target.rect.height(),
                )
                elems = self.grounder.detect_sector_elements(
                    frame,
                    rel_bbox,
                    knowledge_map=self.knowledge_map,
                    max_elements=18,
                )
                for idx, el in enumerate(elems, start=1):
                    ex, ey, ew, eh = el.bbox
                    qrect = _clamp_to_window(QRect(win.left() + ex, win.top() + ey, ew, eh), win)
                    purpose = el.description or _match_editor_purpose(el.label, "preview_transport", self.knowledge_map)
                    detail_targets.append(
                        InteractiveTarget(
                            index=idx,
                            name=el.label,
                            rect=qrect,
                            purpose=purpose,
                            kind="control",
                        )
                    )

            if len(detail_targets) < 2:
                scanned_hits = _load_scanned_controls_in_rect(
                    self.scan_file, target.rect, win, screen_w, screen_h, self.knowledge_map, max_items=18
                )
                if len(scanned_hits) >= 2:
                    detail_targets = scanned_hits

            if not detail_targets:
                subzones = self.grounder.subdivide_box(
                    (target.rect.left(), target.rect.top(), target.rect.width(), target.rect.height()),
                    rows=2,
                    cols=2,
                )
                detail_targets = [
                    InteractiveTarget(
                        index=sz.index,
                        name=sz.label,
                        rect=_clamp_to_window(QRect(sz.bbox[0], sz.bbox[1], sz.bbox[2], sz.bbox[3]), win),
                        purpose=target.purpose,
                        kind="subzone",
                    )
                    for sz in subzones
                ]

            self._targets = detail_targets
            self._level_name = f"sector:{target.name}"
        else:
            r = target.rect
            subzones = self.grounder.subdivide_box((r.left(), r.top(), r.width(), r.height()), rows=2, cols=2)
            self._targets = [
                InteractiveTarget(
                    index=sz.index,
                    name=f"{target.name} [{sz.label}]",
                    rect=_clamp_to_window(QRect(sz.bbox[0], sz.bbox[1], sz.bbox[2], sz.bbox[3]), win),
                    purpose=target.purpose,
                    kind="subzone",
                )
                for sz in subzones
            ]
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
        self._last_frame = None
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
            bx = max(t.rect.left() + 2, min(self.width() - badge_w - 2, t.rect.left() + 2))
            by = max(t.rect.top() + 2, min(self.height() - badge_h - 2, t.rect.top() + 2))
            badge = QRect(bx, by, badge_w, badge_h)

            painter.fillRect(badge, QColor(16, 22, 34, 238))
            painter.setPen(QPen(border_color, 1))
            painter.drawRect(badge)
            painter.setPen(QPen(QColor(255, 255, 255, 255), 1))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
