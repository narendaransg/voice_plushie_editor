from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QRectF, QTimer, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
)

from core.engine import CommandEngine


class ComfortTintOverlay(QWidget):
    """Click-through warm tint filter for long editing sessions."""

    def __init__(self, rgba=(255, 194, 115, 36)):
        super().__init__(None)
        self.rgba = list(rgba)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._sync_geometry()

    def _sync_geometry(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())

    def set_rgba(self, rgba) -> None:
        self.rgba = list(rgba)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        r, g, b, a = self.rgba
        painter.fillRect(self.rect(), QColor(r, g, b, a))


class PlushieAvatarWidget(QWidget):
    """Draggable, squeezable vector plushie with normal and horror states."""

    def __init__(self, engine: CommandEngine, on_squeezed, on_dragged):
        super().__init__(None)
        self.engine = engine
        self.on_squeezed = on_squeezed
        self.on_dragged = on_dragged
        self._drag_offset: Optional[QPoint] = None
        self._squeeze_factor = 1.0

        self.setFixedSize(136, 136)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        self._anim.valueChanged.connect(self._on_anim_value)

    def _on_anim_value(self, value) -> None:
        self._squeeze_factor = float(value)
        self.update()

    def trigger_squeeze(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(0.76)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self.on_squeezed()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            self.trigger_squeeze()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            new_top_left = event.globalPosition().toPoint() - self._drag_offset
            self.window().move(new_top_left)
            self.on_dragged(new_top_left)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        state_key = "horror" if self.engine.horror_active else "normal"
        colors = self.engine.theme.get("plushie", {}).get("colors", {})
        if state_key == "horror":
            colors = {
                **colors,
                **self.engine.theme.get("plushie", {}).get("horror_mode", {}).get("colors", {}),
            }

        primary = QColor(colors.get("primary", "#2A3B55"))
        secondary = QColor(colors.get("secondary", "#C99A5B"))
        accent = QColor(colors.get("accent", "#58A6FF"))
        danger = QColor(colors.get("danger", "#E05252"))

        cx = self.width() / 2.0
        cy = self.height() / 2.0 + 6.0

        # Squash-and-stretch around center
        stretch_x = 2.0 - self._squeeze_factor
        stretch_y = self._squeeze_factor

        painter.save()
        painter.translate(cx, cy)
        painter.scale(stretch_x, stretch_y)

        # Plushie body
        painter.setPen(QPen(accent if self.engine.horror_active else secondary, 2.5))
        painter.setBrush(QBrush(primary))
        painter.drawRoundedRect(QRectF(-34, -22, 68, 62), 24, 24)

        # Plushie head
        painter.setBrush(QBrush(QColor("#F3D5B5") if not self.engine.horror_active else QColor("#D8C3C8")))
        painter.drawEllipse(QRectF(-28, -54, 56, 44))

        # Hair / jacket accent
        painter.setBrush(QBrush(secondary))
        painter.drawChord(QRectF(-28, -55, 56, 30), 0, 180 * 16)

        # Eyes
        eye_color = danger if self.engine.horror_active else QColor("#1B1F24")
        painter.setBrush(QBrush(eye_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-13, -36, 6, 7))
        painter.drawEllipse(QRectF(7, -36, 6, 7))

        # Subtle mouth / expression
        painter.setPen(QPen(eye_color, 2.0))
        if self.engine.horror_active:
            painter.drawLine(-7, -23, 7, -25)
        else:
            painter.drawArc(QRectF(-7, -28, 14, 8), 200 * 16, 140 * 16)

        # Plushie stitch / badge
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(-16, -8, 32, 20), 6, 6)

        painter.restore()


class PlushieOverlayWindow(QWidget):
    """Floating plushie overlay with quick controls, comfort/night modes, and refusal status."""

    def __init__(self, root_dir: Path):
        super().__init__(None)
        self.engine = CommandEngine(root_dir)
        self._comfort_overlay: Optional[ComfortTintOverlay] = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._build_ui()
        self._apply_theme_and_modes()

        # Optional gentle break reminder
        break_mins = int(self.engine.theme.get("comfort_and_night", {}).get("break_reminder_minutes", 45))
        self._break_timer = QTimer(self)
        self._break_timer.setInterval(max(1, break_mins) * 60 * 1000)
        self._break_timer.timeout.connect(self._on_break_reminder)
        self._break_timer.start()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self.avatar = PlushieAvatarWidget(
            engine=self.engine,
            on_squeezed=self._on_plushie_squeezed,
            on_dragged=self._on_plushie_dragged,
        )
        outer.addWidget(self.avatar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.panel = QFrame(self)
        self.panel.setObjectName("ControlPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 8, 10, 8)
        panel_layout.setSpacing(6)

        self.status_label = QLabel(self.engine.prompt("listening"))
        self.status_label.setWordWrap(True)
        self.status_label.setFont(QFont("Segoe UI", 9))
        panel_layout.addWidget(self.status_label)

        row1 = QHBoxLayout()
        self.app_combo = QComboBox()
        for key, prof in self.engine.profiles.items():
            self.app_combo.addItem(prof.get("app_name", key.title()), key)
        current_app = self.engine.settings.get("active_app", "capcut")
        idx = self.app_combo.findData(current_app)
        if idx >= 0:
            self.app_combo.setCurrentIndex(idx)
        self.app_combo.currentIndexChanged.connect(self._on_app_changed)
        row1.addWidget(self.app_combo)

        self.mode_btn = QPushButton()
        self.mode_btn.clicked.connect(self._toggle_compute_mode)
        row1.addWidget(self.mode_btn)

        self.voice_btn = QPushButton()
        self.voice_btn.clicked.connect(self._toggle_voice_mode)
        row1.addWidget(self.voice_btn)
        panel_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.comfort_btn = QPushButton("Comfort")
        self.comfort_btn.setCheckable(True)
        self.comfort_btn.clicked.connect(self._toggle_comfort)
        row2.addWidget(self.comfort_btn)

        self.night_btn = QPushButton("Night")
        self.night_btn.setCheckable(True)
        self.night_btn.clicked.connect(self._toggle_night)
        row2.addWidget(self.night_btn)

        self.horror_btn = QPushButton("Bingo Shift")
        self.horror_btn.setCheckable(True)
        self.horror_btn.clicked.connect(self._toggle_horror_manual)
        row2.addWidget(self.horror_btn)
        panel_layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.test_cut_btn = QPushButton("Test Cut")
        self.test_cut_btn.clicked.connect(lambda: self.handle_utterance("split"))
        row3.addWidget(self.test_cut_btn)

        self.test_cant_btn = QPushButton("Test Can't")
        self.test_cant_btn.clicked.connect(lambda: self.handle_utterance("ripple delete"))
        row3.addWidget(self.test_cant_btn)

        self.quit_btn = QPushButton("Quit")
        self.quit_btn.clicked.connect(self.close)
        row3.addWidget(self.quit_btn)
        panel_layout.addLayout(row3)

        outer.addWidget(self.panel)
        self.setFixedWidth(290)

    def _apply_theme_and_modes(self) -> None:
        state_key = "horror" if self.engine.horror_active else "normal"
        colors = self.engine.theme.get("plushie", {}).get("colors", {})
        if state_key == "horror":
            colors = {
                **colors,
                **self.engine.theme.get("plushie", {}).get("horror_mode", {}).get("colors", {}),
            }

        bg = colors.get("primary", "#2A3B55")
        fg = colors.get("text", "#F5F7FA")
        accent = colors.get("accent", "#58A6FF")

        night_on = bool(self.engine.settings.get("night_mode", False))
        comfort_on = bool(self.engine.settings.get("comfort_mode", False))

        if night_on:
            bg = "#121417"
            fg = "#D0D6DC"

        self.panel.setStyleSheet(
            f"""
            QFrame#ControlPanel {{
                background-color: {bg};
                border: 1.5px solid {accent};
                border-radius: 10px;
            }}
            QLabel {{
                color: {fg};
            }}
            QPushButton, QComboBox {{
                background-color: rgba(255, 255, 255, 0.08);
                color: {fg};
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 5px;
                padding: 3px 6px;
                font-size: 11px;
            }}
            QPushButton:checked {{
                background-color: {accent};
                color: #111317;
                font-weight: bold;
            }}
            """
        )

        cmode = self.engine.settings.get("compute_mode", "cpu").upper()
        vmode = "Always-On" if self.engine.settings.get("voice_mode", "always_on") == "always_on" else "Wake Phrase"
        self.mode_btn.setText(cmode)
        self.voice_btn.setText(vmode)
        self.comfort_btn.setChecked(comfort_on)
        self.night_btn.setChecked(night_on)
        self.horror_btn.setChecked(self.engine.horror_active)

        if comfort_on:
            rgba = self.engine.theme.get("comfort_and_night", {}).get("comfort_tint_rgba", [255, 194, 115, 36])
            if self._comfort_overlay is None:
                self._comfort_overlay = ComfortTintOverlay(rgba)
            else:
                self._comfort_overlay.set_rgba(rgba)
            self._comfort_overlay.show()
        elif self._comfort_overlay is not None:
            self._comfort_overlay.hide()

        self.avatar.update()

    def _on_plushie_squeezed(self) -> None:
        self.status_label.setText(self.engine.prompt("squeeze"))

    def _on_plushie_dragged(self, pos: QPoint) -> None:
        self.engine.settings["overlay_pos"] = [pos.x(), pos.y()]

    def _on_app_changed(self, index: int) -> None:
        app_key = self.app_combo.itemData(index)
        if app_key:
            self.engine.settings["active_app"] = app_key
            self.engine.save_settings()
            self.status_label.setText(self.engine.prompt("listening"))

    def _toggle_compute_mode(self) -> None:
        cur = self.engine.settings.get("compute_mode", "cpu")
        self.engine.settings["compute_mode"] = "gpu" if cur == "cpu" else "cpu"
        self.engine.save_settings()
        self._apply_theme_and_modes()
        self.status_label.setText(self.engine.prompt("listening"))

    def _toggle_voice_mode(self) -> None:
        cur = self.engine.settings.get("voice_mode", "always_on")
        self.engine.settings["voice_mode"] = "wake_phrase" if cur == "always_on" else "always_on"
        self.engine.save_settings()
        self._apply_theme_and_modes()
        self.status_label.setText(self.engine.prompt("listening"))

    def _toggle_comfort(self) -> None:
        self.engine.settings["comfort_mode"] = self.comfort_btn.isChecked()
        self.engine.save_settings()
        self._apply_theme_and_modes()

    def _toggle_night(self) -> None:
        self.engine.settings["night_mode"] = self.night_btn.isChecked()
        self.engine.save_settings()
        self._apply_theme_and_modes()

    def _toggle_horror_manual(self) -> None:
        phrase = "Where's everyone going? Bingo?" if not self.engine.horror_active else "Story of my life"
        self.handle_utterance(phrase)

    def _on_break_reminder(self) -> None:
        self.status_label.setText(self.engine.prompt("comfort_break"))

    def handle_utterance(self, utterance: str, window_ok: bool = True, text_input_focused: bool = False) -> dict:
        app_key = self.engine.settings.get("active_app", "capcut")
        result = self.engine.resolve_command(
            utterance=utterance,
            app_key=app_key,
            window_ok=window_ok,
            text_input_focused=text_input_focused,
        )
        self._apply_theme_and_modes()
        self.status_label.setText(result.get("message", ""))
        return result

    def closeEvent(self, event) -> None:
        if self._comfort_overlay is not None:
            self._comfort_overlay.close()
        self.engine.save_settings()
        super().closeEvent(event)
