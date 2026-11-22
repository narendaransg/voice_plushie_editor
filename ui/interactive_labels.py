import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


@dataclass
class InteractiveTarget:
    index: int
    name: str
    rect: QRect

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


def _scan_uia_targets(screen_w: int, screen_h: int, max_items: int = 60) -> List[InteractiveTarget]:
    """Scan interactive UI controls using Windows UI Automation ControlViewWalker."""
    try:
        import uiautomation as auto  # type: ignore
    except Exception:
        return []

    targets: List[InteractiveTarget] = []
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

            while stack and len(targets) < max_items and visited < 1500:
                ctrl = stack.pop()
                visited += 1
                try:
                    if ctrl.IsOffscreen or not ctrl.IsEnabled:
                        continue
                    rect = ctrl.BoundingRectangle
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w < 12 or h < 12 or w > screen_w * 0.92 or h > screen_h * 0.92:
                        continue
                    if rect.right < 0 or rect.bottom < 0 or rect.left > screen_w or rect.top > screen_h:
                        continue

                    if ctrl.ControlType in interactive_types:
                        qrect = QRect(rect.left, rect.top, w, h)
                        if any(
                            abs(t.rect.left() - qrect.left()) < 10
                            and abs(t.rect.top() - qrect.top()) < 10
                            and abs(t.rect.width() - qrect.width()) < 10
                            and abs(t.rect.height() - qrect.height()) < 10
                            for t in targets
                        ):
                            continue

                        label = (ctrl.Name or "").strip()
                        targets.append(
                            InteractiveTarget(
                                index=len(targets) + 1,
                                name=label,
                                rect=qrect,
                            )
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

    return targets


def _build_keytip_zone_targets(screen_w: int, screen_h: int) -> List[InteractiveTarget]:
    """Generate MS-Office KeyTip-style badges over visible editor/app regions when UIA is sparse."""
    win = _get_foreground_window_rect(screen_w, screen_h)
    wx, wy, ww, wh = win.left(), win.top(), win.width(), win.height()

    zones: List[Tuple[str, QRect]] = [
        # Top bar / header actions
        ("Top Left", QRect(wx + int(ww * 0.08), wy + 8, int(ww * 0.25), 36)),
        ("Top Center", QRect(wx + int(ww * 0.45), wy + 8, int(ww * 0.20), 36)),
        ("Share/Export", QRect(wx + int(ww * 0.80), wy + 8, int(ww * 0.16), 36)),
        # Left rail tools
        ("Media", QRect(wx + 4, wy + int(wh * 0.10), 56, 56)),
        ("Record", QRect(wx + 4, wy + int(wh * 0.19), 56, 56)),
        ("Library", QRect(wx + 4, wy + int(wh * 0.28), 56, 56)),
        ("Templates", QRect(wx + 4, wy + int(wh * 0.37), 56, 56)),
        ("Text", QRect(wx + 4, wy + int(wh * 0.46), 56, 56)),
        ("Transitions", QRect(wx + 4, wy + int(wh * 0.55), 56, 56)),
        # Left drawer action area
        ("Drawer Action", QRect(wx + int(ww * 0.09), wy + int(wh * 0.14), int(ww * 0.14), 44)),
        # Center canvas / preview
        ("Canvas", QRect(wx + int(ww * 0.36), wy + int(wh * 0.28), int(ww * 0.28), int(wh * 0.24))),
        # Transport / Play bar
        ("Play", QRect(wx + int(ww * 0.48), wy + int(wh * 0.61), 44, 36)),
        ("Undo/Redo", QRect(wx + int(ww * 0.38), wy + int(wh * 0.61), 80, 36)),
        # Right inspector rail
        ("Captions", QRect(wx + ww - 60, wy + int(wh * 0.10), 54, 48)),
        ("Audio", QRect(wx + ww - 60, wy + int(wh * 0.19), 54, 48)),
        ("Fade", QRect(wx + ww - 60, wy + int(wh * 0.28), 54, 48)),
        ("Filters", QRect(wx + ww - 60, wy + int(wh * 0.37), 54, 48)),
        ("Effects", QRect(wx + ww - 60, wy + int(wh * 0.46), 54, 48)),
        ("Adjust", QRect(wx + ww - 60, wy + int(wh * 0.55), 54, 48)),
        ("Upscale", QRect(wx + ww - 60, wy + int(wh * 0.64), 54, 48)),
        ("Speed", QRect(wx + ww - 60, wy + int(wh * 0.73), 54, 48)),
        # Timeline tracks
        ("Video Track", QRect(wx + int(ww * 0.28), wy + int(wh * 0.80), int(ww * 0.35), 48)),
        ("Audio Track", QRect(wx + int(ww * 0.28), wy + int(wh * 0.88), int(ww * 0.35), 36)),
        ("Zoom Controls", QRect(wx + ww - 160, wy + wh - 42, 140, 30)),
    ]

    targets: List[InteractiveTarget] = []
    for idx, (label, rect) in enumerate(zones, start=1):
        targets.append(InteractiveTarget(index=idx, name=label, rect=rect))
    return targets


class InteractiveLabelOverlay(QWidget):
    """Click-through overlay drawing MS-Office KeyTip-style numbered badges over interactive controls/zones."""

    def __init__(self):
        super().__init__(None)
        self._targets: List[InteractiveTarget] = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def scan_and_show(self, screen_w: int, screen_h: int) -> int:
        targets = _scan_uia_targets(screen_w, screen_h)
        if len(targets) < 6:
            targets = _build_keytip_zone_targets(screen_w, screen_h)

        self._targets = targets
        self.setGeometry(0, 0, screen_w, screen_h)
        if targets:
            self.show()
            self.raise_()
            self.update()
        else:
            self.hide()
        return len(targets)

    def clear_labels(self) -> None:
        self._targets = []
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
            painter.setPen(QPen(QColor(255, 204, 48, 220), 2))
            painter.drawRect(t.rect)

            tag = str(t.index) if not t.name else f"{t.index}"
            badge_w = 28
            badge_h = 20
            bx = max(0, min(self.width() - badge_w, t.rect.left()))
            by = max(0, min(self.height() - badge_h, t.rect.top()))
            badge = QRect(bx, by, badge_w, badge_h)

            painter.fillRect(badge, QColor(18, 22, 32, 240))
            painter.setPen(QPen(QColor(255, 215, 64, 255), 1))
            painter.drawRect(badge)
            painter.setPen(QPen(QColor(255, 255, 255, 255), 1))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
