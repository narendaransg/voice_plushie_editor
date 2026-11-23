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
    "drawer": {
        "title": "Asset & Media Drawer",
        "purpose": "Import video/audio clips, browse presets, and drag items onto the timeline.",
    },
    "preview": {
        "title": "Preview Monitor & Play Controls",
        "purpose": "Inspect the video frame, play/pause playback, step frames, and scrub the playhead.",
    },
    "right_rail": {
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
    kind: str = "group"  # "sector", "group", "subzone", "drop_target"

    @property
    def center(self) -> Tuple[int, int]:
        return self.rect.center().x(), self.rect.center().y()


def _get_dpi_scale() -> float:
    app_inst = QApplication.instance()
    if app_inst is not None:
        screen = app_inst.primaryScreen()
        if screen is not None:
            dpr = float(screen.devicePixelRatio())
            if dpr > 0.5:
                return dpr
    return 1.0


def _get_foreground_window_rect(screen_w: int, screen_h: int) -> QRect:
    scale = _get_dpi_scale()
    if hasattr(ctypes, "windll"):
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            r = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(r)):
                left = max(0, int(round(r.left / scale)))
                top = max(0, int(round(r.top / scale)))
                right = min(screen_w, int(round(r.right / scale)))
                bottom = min(screen_h, int(round(r.bottom / scale)))
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
    low = (label or "").strip().lower().replace(" ", "_")
    active_map: Dict[str, str] = {
        k: v["purpose"] for k, v in VIDEO_EDITOR_UI_MAP.items()
    }
    if knowledge_map:
        active_map.update({k.lower(): v for k, v in knowledge_map.items() if v})

    if low in active_map:
        return active_map[low]
    plain = (label or "").strip().lower()
    for key, desc in active_map.items():
        if key and re.search(rf"\b{re.escape(key.replace('_', ' '))}\b", plain):
            return desc
    if fallback_key in active_map:
        return active_map[fallback_key]
    return (
        f"Interactive region '{label}' inside the active video editor."
        if label
        else "Interactive region in the active video editor."
    )


def _dynamic_plus_layout_sectors(
    win: QRect,
    detected: List[InteractiveTarget],
    knowledge_map: Optional[Dict[str, str]] = None,
) -> List[InteractiveTarget]:
    """Ensure multi-sector coverage even when CV detects only 1-2 dominant regions."""
    wx, wy, ww, wh = win.left(), win.top(), win.width(), win.height()
    header_h = max(36, min(52, int(wh * 0.055)))
    rail_w = max(44, min(62, int(ww * 0.045)))
    right_w = max(48, min(70, int(ww * 0.052)))
    timeline_h = max(150, min(int(wh * 0.34), wh - header_h - 140))
    main_top = wy + header_h + 2
    main_h = max(120, wh - header_h - timeline_h - 6)
    drawer_w = max(150, min(int(ww * 0.20), ww - rail_w - right_w - 240))
    preview_x = wx + rail_w + drawer_w + 4
    preview_w = max(180, (wx + ww - right_w - 4) - preview_x)

    candidates: List[Tuple[str, QRect, str]] = [
        ("Header", QRect(wx + rail_w, wy + 2, max(120, ww - rail_w - right_w), header_h), "header"),
        ("Left Rail", QRect(wx + 2, main_top, rail_w, main_h + timeline_h), "left_rail"),
        ("Media Drawer", QRect(wx + rail_w + 2, main_top, drawer_w, main_h), "drawer"),
        ("Preview", QRect(preview_x, main_top, preview_w, main_h), "preview"),
        ("Right Rail", QRect(wx + ww - right_w - 2, main_top, right_w, main_h), "right_rail"),
        ("Timeline", QRect(wx + rail_w + 2, main_top + main_h + 2, max(200, ww - rail_w - right_w - 4), timeline_h), "timeline"),
    ]

    result: List[InteractiveTarget] = []
    # Keep genuinely distinct CV regions that are not tiny single-card boxes
    for d in detected:
        if d.rect.width() >= int(ww * 0.14) and d.rect.height() >= int(wh * 0.12):
            result.append(
                InteractiveTarget(
                    index=len(result) + 1,
                    name=d.name,
                    rect=_clamp_to_window(d.rect, win),
                    purpose=d.purpose,
                    kind="sector",
                )
            )
        if len(result) >= 6:
            break

    if len(result) < 4:
        result = []
        for idx, (title, rect, key) in enumerate(candidates, start=1):
            result.append(
                InteractiveTarget(
                    index=idx,
                    name=title,
                    rect=_clamp_to_window(rect, win),
                    purpose=_match_editor_purpose(title, key, knowledge_map),
                    kind="sector",
                )
            )

    return result


def _load_scanned_controls_in_rect(
    scan_file: Optional[Path],
    region: QRect,
    bounds: QRect,
    screen_w: int,
    screen_h: int,
    knowledge_map: Optional[Dict[str, str]] = None,
    max_items: int = 14,
) -> List[InteractiveTarget]:
    if scan_file is None or not scan_file.exists():
        return []
    try:
        data: Dict[str, Any] = json.loads(scan_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    scale = _get_dpi_scale()
    raw_controls = data.get("controls") or []
    targets: List[InteractiveTarget] = []
    for item in raw_controls:
        if len(targets) >= max_items:
            break
        r = item.get("rect") or {}
        left = int(round(int(r.get("left", 0)) / scale))
        top = int(round(int(r.get("top", 0)) / scale))
        right = int(round(int(r.get("right", 0)) / scale))
        bottom = int(round(int(r.get("bottom", 0)) / scale))
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
        name = (item.get("name") or "").strip() or f"Group {len(targets) + 1}"
        purpose = (item.get("purpose") or "").strip() or _match_editor_purpose(name, "preview", knowledge_map)
        targets.append(
            InteractiveTarget(
                index=len(targets) + 1,
                name=name,
                rect=qrect,
                purpose=purpose,
                kind="group",
            )
        )
    return targets


class InteractiveLabelOverlay(QWidget):
    """Dynamic sector -> sub-group -> drop-target overlay with instant hide/repaint."""

    def __init__(self, scan_file: Optional[Path] = None):
        super().__init__(None)
        self.scan_file = scan_file
        self.grounder = VisionGrounder()
        self.knowledge_map: Dict[str, str] = {}
        self._targets: List[InteractiveTarget] = []
        self._detected_sectors: List[InteractiveTarget] = []
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
        scale = _get_dpi_scale()
        try:
            excl_tuple = None
            if exclude_rect is not None and exclude_rect.isValid():
                excl_tuple = (
                    int(round(exclude_rect.left() * scale)),
                    int(round(exclude_rect.top() * scale)),
                    int(round(exclude_rect.width() * scale)),
                    int(round(exclude_rect.height() * scale)),
                )
            frame = self.grounder.capture_window_region(
                int(round(win.left() * scale)),
                int(round(win.top() * scale)),
                int(round(win.width() * scale)),
                int(round(win.height() * scale)),
                exclude_rect=excl_tuple,
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

        raw_detected: List[InteractiveTarget] = []
        if frame is not None:
            scale = _get_dpi_scale()
            panels = self.grounder.detect_panels(frame, max_panels=8)
            for idx, p in enumerate(panels, start=1):
                px, py, pw, ph = p.bbox
                qrect = _clamp_to_window(
                    QRect(
                        win.left() + int(round(px / scale)),
                        win.top() + int(round(py / scale)),
                        max(18, int(round(pw / scale))),
                        max(18, int(round(ph / scale))),
                    ),
                    win,
                )
                raw_detected.append(
                    InteractiveTarget(
                        index=idx,
                        name=p.label,
                        rect=qrect,
                        purpose=_match_editor_purpose(p.label, "timeline", self.knowledge_map),
                        kind="sector",
                    )
                )

        sectors = _dynamic_plus_layout_sectors(win, raw_detected, self.knowledge_map)
        self._detected_sectors = list(sectors)
        self._targets = sectors
        self._level_name = "sectors"
        self.setGeometry(0, 0, screen_w, screen_h)
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
        scale = _get_dpi_scale()

        if target.kind == "sector" and not force_subzone:
            frame = self._last_frame if self._last_frame is not None else self._capture_clean_window(win)
            sub_groups: List[InteractiveTarget] = []

            if frame is not None:
                rel_bbox = (
                    max(0, int(round((target.rect.left() - win.left()) * scale))),
                    max(0, int(round((target.rect.top() - win.top()) * scale))),
                    max(12, int(round(target.rect.width() * scale))),
                    max(12, int(round(target.rect.height() * scale))),
                )
                elems = self.grounder.detect_sector_elements(
                    frame,
                    rel_bbox,
                    knowledge_map=self.knowledge_map,
                    max_elements=14,
                )
                for idx, el in enumerate(elems, start=1):
                    ex, ey, ew, eh = el.bbox
                    qrect = _clamp_to_window(
                        QRect(
                            win.left() + int(round(ex / scale)),
                            win.top() + int(round(ey / scale)),
                            max(16, int(round(ew / scale))),
                            max(14, int(round(eh / scale))),
                        ),
                        win,
                    )
                    purpose = el.description or _match_editor_purpose(el.label, "preview", self.knowledge_map)
                    sub_groups.append(
                        InteractiveTarget(
                            index=idx,
                            name=el.label,
                            rect=qrect,
                            purpose=purpose,
                            kind="group",
                        )
                    )

            if len(sub_groups) < 2:
                scanned = _load_scanned_controls_in_rect(
                    self.scan_file, target.rect, win, screen_w, screen_h, self.knowledge_map, max_items=14
                )
                if len(scanned) >= 2:
                    sub_groups = scanned

            if not sub_groups:
                subzones = self.grounder.subdivide_box(
                    (target.rect.left(), target.rect.top(), target.rect.width(), target.rect.height()),
                    rows=2,
                    cols=2,
                )
                sub_groups = [
                    InteractiveTarget(
                        index=sz.index,
                        name=f"Group {sz.index}",
                        rect=_clamp_to_window(QRect(sz.bbox[0], sz.bbox[1], sz.bbox[2], sz.bbox[3]), win),
                        purpose=target.purpose,
                        kind="group",
                    )
                    for sz in subzones
                ]

            self._targets = sub_groups
            self._level_name = "groups"
        else:
            r = target.rect
            subzones = self.grounder.subdivide_box((r.left(), r.top(), r.width(), r.height()), rows=2, cols=2)
            self._targets = [
                InteractiveTarget(
                    index=sz.index,
                    name=f"Spot {sz.index}",
                    rect=_clamp_to_window(QRect(sz.bbox[0], sz.bbox[1], sz.bbox[2], sz.bbox[3]), win),
                    purpose=target.purpose,
                    kind="subzone",
                )
                for sz in subzones
            ]
            self._level_name = "spots"

        self.setGeometry(0, 0, screen_w, screen_h)
        self.show()
        self.raise_()
        self.update()
        return len(self._targets)

    def show_drop_targets(self, screen_w: int, screen_h: int) -> int:
        """Show drop destinations (timeline slots, overlay track, preview) while holding a dragged clip."""
        self._history.append((self._level_name, list(self._targets)))
        win = self._last_win_rect or _get_foreground_window_rect(screen_w, screen_h)

        timeline_rect: Optional[QRect] = None
        preview_rect: Optional[QRect] = None
        for sec in self._detected_sectors:
            if "timeline" in sec.name.lower() and timeline_rect is None:
                timeline_rect = sec.rect
            elif "preview" in sec.name.lower() and preview_rect is None:
                preview_rect = sec.rect

        if timeline_rect is None:
            timeline_rect = QRect(
                win.left() + int(win.width() * 0.18),
                win.top() + int(win.height() * 0.72),
                max(220, int(win.width() * 0.74)),
                max(120, int(win.height() * 0.24)),
            )
        if preview_rect is None:
            preview_rect = QRect(
                win.left() + int(win.width() * 0.30),
                win.top() + int(win.height() * 0.16),
                max(200, int(win.width() * 0.52)),
                max(140, int(win.height() * 0.44)),
            )

        tx, ty, tw, th = timeline_rect.left(), timeline_rect.top(), timeline_rect.width(), timeline_rect.height()
        drop_specs = [
            ("Timeline Start", QRect(tx + 12, ty + int(th * 0.45), max(70, tw // 3 - 12), max(32, th // 3))),
            ("Timeline Mid", QRect(tx + tw // 3, ty + int(th * 0.45), max(70, tw // 3), max(32, th // 3))),
            ("Timeline End", QRect(tx + (2 * tw) // 3, ty + int(th * 0.45), max(70, tw // 3 - 12), max(32, th // 3))),
            ("Overlay Track", QRect(tx + tw // 4, ty + int(th * 0.18), max(80, tw // 2), max(26, th // 4))),
            ("Preview Canvas", QRect(preview_rect.center().x() - 75, preview_rect.center().y() - 25, 150, 50)),
        ]

        self._targets = [
            InteractiveTarget(
                index=i,
                name=label,
                rect=_clamp_to_window(rect, win),
                purpose=f"Drop dragged media onto {label}.",
                kind="drop_target",
            )
            for i, (label, rect) in enumerate(drop_specs, start=1)
        ]
        self._level_name = "drop_targets"
        self.setGeometry(0, 0, screen_w, screen_h)
        self.show()
        self.raise_()
        self.update()
        app_inst = QApplication.instance()
        if app_inst is not None:
            app_inst.processEvents()
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
        else:
            self.clear_labels()
            return None
        return self._level_name

    def clear_labels(self) -> None:
        self._history.clear()
        self._targets = []
        self._level_name = "sectors"
        self._last_frame = None
        self.repaint()
        self.hide()
        app_inst = QApplication.instance()
        if app_inst is not None:
            app_inst.processEvents()

    def close_overlay(self) -> None:
        self.clear_labels()
        self.close()

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
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        draw_boxes = self._level_name == "sectors"

        for t in self._targets:
            if draw_boxes:
                border_color = QColor(80, 210, 255, 220)
                painter.setPen(QPen(border_color, 2))
                painter.drawRect(t.rect)
                bx = max(2, min(self.width() - 140, t.rect.left() + 4))
                by = max(2, min(self.height() - 24, t.rect.top() + 4))
                pill_color = QColor(14, 24, 38, 242)
                accent_color = QColor(80, 210, 255, 235)
            else:
                cx, cy = t.center
                badge_w_est = min(136, max(36, len(f"{t.index}:{t.name[:13]}") * 7 + 14))
                bx = max(2, min(self.width() - badge_w_est - 2, cx - badge_w_est // 2))
                by = max(2, min(self.height() - 24, cy - 11))
                if self._level_name == "drop_targets":
                    pill_color = QColor(36, 16, 44, 248)
                    accent_color = QColor(232, 121, 249, 250)
                elif self._level_name == "groups":
                    pill_color = QColor(24, 18, 8, 245)
                    accent_color = QColor(255, 198, 45, 240)
                else:
                    pill_color = QColor(16, 30, 24, 245)
                    accent_color = QColor(72, 224, 156, 240)

            tag = f"{t.index}" if not t.name else f"{t.index}:{t.name[:13]}"
            badge_w = max(32, min(140, len(tag) * 7 + 12))
            badge_h = 20
            badge = QRect(bx, by, badge_w, badge_h)

            painter.fillRect(badge, pill_color)
            painter.setPen(QPen(accent_color, 1))
            painter.drawRect(badge)
            painter.setPen(QPen(QColor(255, 255, 255, 255), 1))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
