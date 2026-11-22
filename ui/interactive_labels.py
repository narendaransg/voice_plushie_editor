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


def _scan_uia_targets(screen_w: int, screen_h: int, max_items: int = 60) -> List[InteractiveTarget]:
    """Scan interactive UI controls using Windows UI Automation when available."""
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

            walker = auto.ControlWalker(auto.TreeWalkerRawViewWalker)
            stack = [fg]
            visited = 0

            while stack and len(targets) < max_items and visited < 600:
                ctrl = stack.pop()
                visited += 1
                try:
                    if ctrl.IsOffscreen or not ctrl.IsEnabled:
                        continue
                    rect = ctrl.BoundingRectangle
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w < 14 or h < 14 or w > screen_w * 0.9 or h > screen_h * 0.9:
                        continue
                    if rect.right < 0 or rect.bottom < 0 or rect.left > screen_w or rect.top > screen_h:
                        continue

                    if ctrl.ControlType in interactive_types:
                        qrect = QRect(rect.left, rect.top, w, h)
                        # Skip duplicate overlapping rectangles that are almost identical
                        if any(
                            abs(t.rect.left() - qrect.left()) < 8
                            and abs(t.rect.top() - qrect.top()) < 8
                            and abs(t.rect.width() - qrect.width()) < 8
                            and abs(t.rect.height() - qrect.height()) < 8
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


def _scan_win32_child_targets(screen_w: int, screen_h: int, max_items: int = 40) -> List[InteractiveTarget]:
    """Fallback Win32 child window scanner when UIAutomation package is unavailable."""
    if not hasattr(ctypes, "windll"):
        return []

    user32 = ctypes.windll.user32
    targets: List[InteractiveTarget] = []

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return []

    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(child_hwnd, _lparam):
        if len(targets) >= max_items:
            return False
        if not user32.IsWindowVisible(child_hwnd) or not user32.IsWindowEnabled(child_hwnd):
            return True

        r = wintypes.RECT()
        if not user32.GetWindowRect(child_hwnd, ctypes.byref(r)):
            return True

        w = r.right - r.left
        h = r.bottom - r.top
        if w < 16 or h < 14 or w > screen_w * 0.85 or h > screen_h * 0.85:
            return True
        if r.right < 0 or r.bottom < 0 or r.left > screen_w or r.top > screen_h:
            return True

        buf = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(child_hwnd, buf, 128)
        title = buf.value.strip()

        qrect = QRect(r.left, r.top, w, h)
        if not any(
            abs(t.rect.left() - qrect.left()) < 8 and abs(t.rect.top() - qrect.top()) < 8
            for t in targets
        ):
            targets.append(InteractiveTarget(index=len(targets) + 1, name=title, rect=qrect))
        return True

    user32.EnumChildWindows(hwnd, enum_proc_type(_enum_cb), 0)
    return targets


class InteractiveLabelOverlay(QWidget):
    """Click-through overlay drawing numbered badges over interactive UI elements."""

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
        if not targets:
            targets = _scan_win32_child_targets(screen_w, screen_h)

        self._targets = targets
        self.setGeometry(0, 0, screen_w, screen_h)
        if targets:
            self.show()
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
            # Subtle highlight border around interactive control
            painter.setPen(QPen(QColor(255, 200, 50, 210), 2))
            painter.drawRect(t.rect)

            tag = str(t.index)
            if t.name:
                short_name = t.name[:14] + ("…" if len(t.name) > 14 else "")
                tag = f"{t.index}:{short_name}"

            badge_w = max(24, min(145, len(tag) * 8 + 12))
            badge_h = 20
            bx = max(0, min(self.width() - badge_w, t.rect.left()))
            by = max(0, min(self.height() - badge_h, t.rect.top() - badge_h // 2))
            badge = QRect(bx, by, badge_w, badge_h)

            painter.fillRect(badge, QColor(20, 24, 34, 235))
            painter.setPen(QPen(QColor(255, 220, 80, 255), 1))
            painter.drawRect(badge)
            painter.setPen(QPen(QColor(255, 255, 255, 255), 1))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)
