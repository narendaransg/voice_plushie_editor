from typing import Optional, Tuple

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class VoiceGridOverlay(QWidget):
    """Click-through transparent numbered grid overlay for instant voice cursor jumps."""

    def __init__(self, cols: int = 8, rows: int = 6):
        super().__init__(None)
        self.cols = cols
        self.rows = rows
        self._zoom_rect: Optional[QRect] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def show_full_screen_grid(self, screen_w: int, screen_h: int, cols: int = 8, rows: int = 6) -> None:
        self.cols = cols
        self.rows = rows
        self._zoom_rect = None
        self.setGeometry(0, 0, screen_w, screen_h)
        self.show()
        self.update()

    def show_micro_grid(self, screen_w: int, screen_h: int, center_x: int, center_y: int, box_size: int = 240) -> None:
        self.cols = 3
        self.rows = 3
        half = box_size // 2
        left = max(0, min(screen_w - box_size, center_x - half))
        top = max(0, min(screen_h - box_size, center_y - half))
        self._zoom_rect = QRect(left, top, box_size, box_size)
        self.setGeometry(0, 0, screen_w, screen_h)
        self.show()
        self.update()

    def max_cell_number(self) -> int:
        return self.cols * self.rows

    def get_cell_center(self, cell_num: int) -> Optional[Tuple[int, int]]:
        total = self.max_cell_number()
        if cell_num < 1 or cell_num > total:
            return None

        bounds = self._zoom_rect if self._zoom_rect is not None else self.rect()
        idx = cell_num - 1
        r = idx // self.cols
        c = idx % self.cols

        cell_w = bounds.width() / float(self.cols)
        cell_h = bounds.height() / float(self.rows)

        cx = int(round(bounds.left() + (c + 0.5) * cell_w))
        cy = int(round(bounds.top() + (r + 0.5) * cell_h))
        return cx, cy

    def paintEvent(self, event) -> None:
        _ = event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bounds = self._zoom_rect if self._zoom_rect is not None else self.rect()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return

        # Subtle backdrop tint
        painter.fillRect(bounds, QColor(12, 18, 28, 45))

        pen = QPen(QColor(90, 190, 255, 175), 1)
        painter.setPen(pen)

        cell_w = bounds.width() / float(self.cols)
        cell_h = bounds.height() / float(self.rows)

        font_size = 13 if self._zoom_rect is None else 12
        painter.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))

        num = 1
        for r in range(self.rows):
            for c in range(self.cols):
                x = int(round(bounds.left() + c * cell_w))
                y = int(round(bounds.top() + r * cell_h))
                w = int(round(cell_w))
                h = int(round(cell_h))
                cell_rect = QRect(x, y, w, h)

                painter.setPen(QPen(QColor(90, 190, 255, 150), 1))
                painter.drawRect(cell_rect)

                # Badge behind number for readability on light/dark editor backgrounds
                badge_w, badge_h = 34, 22
                bx = x + (w - badge_w) // 2
                by = y + (h - badge_h) // 2
                badge_rect = QRect(bx, by, badge_w, badge_h)
                painter.fillRect(badge_rect, QColor(15, 23, 36, 200))
                painter.setPen(QPen(QColor(245, 250, 255, 245), 1))
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, str(num))
                num += 1
