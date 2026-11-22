import json
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QColorDialog,
    QFileDialog,
    QCheckBox,
    QTextEdit,
    QMessageBox,
)


def slugify_theme_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "custom_theme"


class ColorPickerButton(QPushButton):
    def __init__(self, initial_hex: str = "#2A3B55"):
        super().__init__(initial_hex)
        self._hex = initial_hex
        self._refresh_style()
        self.clicked.connect(self._pick)

    def _refresh_style(self) -> None:
        self.setText(self._hex)
        self.setStyleSheet(
            f"background-color: {self._hex}; color: #FFFFFF; border: 1px solid #888; padding: 4px 8px;"
        )

    def _pick(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._hex), self, "Select Color")
        if chosen.isValid():
            self._hex = chosen.name().upper()
            self._refresh_style()

    def hex_value(self) -> str:
        return self._hex

    def set_hex_value(self, hex_code: str) -> None:
        self._hex = hex_code
        self._refresh_style()


class IdentityPage(QWizardPage):
    def __init__(self, root_dir: Path):
        super().__init__()
        self.root_dir = root_dir
        self.setTitle("Step 1: Theme Identity & Starting Base")
        self.setSubTitle("Name your theme and choose an existing theme to clone defaults from.")

        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g., Attack on Titan — Mikasa")
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g., aot_mikasa")

        self.name_edit.textChanged.connect(
            lambda txt: self.id_edit.setText(slugify_theme_id(txt))
        )

        self.base_combo = QComboBox()
        themes_dir = self.root_dir / "themes"
        if themes_dir.exists():
            for d in sorted(themes_dir.iterdir()):
                if (d / "theme.json").exists():
                    self.base_combo.addItem(d.name, d.name)

        self.activate_chk = QCheckBox("Set as active theme after saving")
        self.activate_chk.setChecked(True)

        layout.addRow("Display Name:", self.name_edit)
        layout.addRow("Theme Folder ID:", self.id_edit)
        layout.addRow("Clone Base From:", self.base_combo)
        layout.addRow("", self.activate_chk)

        self.registerField("display_name*", self.name_edit)
        self.registerField("theme_id*", self.id_edit)


class NormalAppearancePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 2: Normal State Palette & Optional Plushie Sprites")
        self.setSubTitle("Pick colors for the default calm state. Leave sprite paths empty to use built-in vector art.")

        layout = QFormLayout(self)
        self.colors: Dict[str, ColorPickerButton] = {
            "primary": ColorPickerButton("#2A3B55"),
            "secondary": ColorPickerButton("#C99A5B"),
            "accent": ColorPickerButton("#58A6FF"),
            "text": ColorPickerButton("#F5F7FA"),
            "danger": ColorPickerButton("#E05252"),
        }
        for key, btn in self.colors.items():
            layout.addRow(f"{key.title()} Color:", btn)

        self.idle_sprite = QLineEdit()
        self.squeeze_sprite = QLineEdit()
        layout.addRow("Normal Idle PNG (optional):", self._file_row(self.idle_sprite))
        layout.addRow("Normal Squeeze PNG (optional):", self._file_row(self.squeeze_sprite))

    def _file_row(self, target_edit: QLineEdit) -> QWidget:
        from PySide6.QtWidgets import QWidget
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse(target_edit))
        row.addWidget(target_edit)
        row.addWidget(btn)
        return box

    def _browse(self, target_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PNG Sprite", "", "PNG Images (*.png)")
        if path:
            target_edit.setText(path)


class TransformationPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 3: Dramatic / Battle Transformation State")
        self.setSubTitle("Configure the spoken quote that transforms the plushie and the revert phrase.")

        layout = QFormLayout(self)
        self.triggers_edit = QLineEdit("where's everyone going bingo")
        self.triggers_edit.setPlaceholderText("Comma-separated phrases (e.g. this world is cruel, if i can't i'll just die)")
        self.reverts_edit = QLineEdit("story of my life")
        self.reverts_edit.setPlaceholderText("Comma-separated revert phrases (e.g. i'm going home)")

        layout.addRow("Transform Trigger Phrases:", self.triggers_edit)
        layout.addRow("Revert Phrases:", self.reverts_edit)

        self.colors: Dict[str, ColorPickerButton] = {
            "primary": ColorPickerButton("#1A0D10"),
            "secondary": ColorPickerButton("#8F1D2C"),
            "accent": ColorPickerButton("#39D353"),
            "text": ColorPickerButton("#F2E9E4"),
            "danger": ColorPickerButton("#FF2A3C"),
        }
        for key, btn in self.colors.items():
            layout.addRow(f"Transformed {key.title()}:", btn)

        self.horror_idle_sprite = QLineEdit()
        self.horror_squeeze_sprite = QLineEdit()
        layout.addRow("Transformed Idle PNG (optional):", self._file_row(self.horror_idle_sprite))
        layout.addRow("Transformed Squeeze PNG (optional):", self._file_row(self.horror_squeeze_sprite))

    def _file_row(self, target_edit: QLineEdit):
        from PySide6.QtWidgets import QWidget
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton("Browse...")
        btn.clicked.connect(lambda: self._browse(target_edit))
        row.addWidget(target_edit)
        row.addWidget(btn)
        return box

    def _browse(self, target_edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select PNG Sprite", "", "PNG Images (*.png)")
        if path:
            target_edit.setText(path)


class PromptsPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 4: Voice Lines & Explicit 'Can't Do That' Refusals")
        self.setSubTitle("Placeholders available: {action}, {app}, {keys}, {mode}, {voice_mode}")

        layout = QFormLayout(self)
        self.fields: Dict[str, QLineEdit] = {
            "listening": QLineEdit("Ready ({mode} / {app}) — {voice_mode}."),
            "executed": QLineEdit("Done: '{action}' [{keys}]."),
            "cant_do_unmapped": QLineEdit("Can't do '{action}' — not mapped in {app}."),
            "cant_do_focus": QLineEdit("Can't send '{keys}' — {app} isn't focused or a text box is active."),
            "cant_do_unsupported": QLineEdit("Can't do '{action}' — unsupported in current setup."),
            "squeeze": QLineEdit("Squeak! Plushie squeezed."),
            "horror_enter": QLineEdit("Mode shifted!"),
            "horror_exit": QLineEdit("Back to normal mode."),
            "comfort_break": QLineEdit("Long edit stretch — want a quick break?"),
        }
        for key, edit in self.fields.items():
            layout.addRow(f"{key}:", edit)


class SummaryPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Step 5: Review & Save Theme")
        self.setSubTitle("Verify generated files before writing to themes/<theme_id>/.")
        layout = QVBoxLayout(self)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview)

    def initializePage(self) -> None:
        wiz: ThemeWizard = self.wizard()  # type: ignore
        data = wiz.build_theme_dict()
        self.preview.setPlainText(json.dumps(data, indent=2))


class ThemeWizard(QWizard):
    """Step-by-step wizard to create or customize plushie themes without editing JSON."""

    def __init__(self, root_dir: Path, parent=None):
        super().__init__(parent)
        self.root_dir = Path(root_dir)
        self.setWindowTitle("Plushie Theme Customization Wizard")
        self.resize(560, 520)

        self.identity_page = IdentityPage(self.root_dir)
        self.normal_page = NormalAppearancePage()
        self.transform_page = TransformationPage()
        self.prompts_page = PromptsPage()
        self.summary_page = SummaryPage()

        self.addPage(self.identity_page)
        self.addPage(self.normal_page)
        self.addPage(self.transform_page)
        self.addPage(self.prompts_page)
        self.addPage(self.summary_page)

        self.identity_page.base_combo.currentIndexChanged.connect(self._load_base_defaults)
        if self.identity_page.base_combo.count() > 0:
            self._load_base_defaults()

    def _load_base_defaults(self) -> None:
        base_id = self.identity_page.base_combo.currentData()
        if not base_id:
            return
        base_dir = self.root_dir / "themes" / base_id
        try:
            theme = json.loads((base_dir / "theme.json").read_text(encoding="utf-8"))
            prompts = json.loads((base_dir / "prompts.json").read_text(encoding="utf-8"))
        except Exception:
            return

        norm_colors = theme.get("plushie", {}).get("colors", {})
        for k, btn in self.normal_page.colors.items():
            if k in norm_colors:
                btn.set_hex_value(norm_colors[k])

        horror = theme.get("plushie", {}).get("horror_mode", {})
        self.transform_page.triggers_edit.setText(", ".join(horror.get("triggers", [])))
        self.transform_page.reverts_edit.setText(", ".join(horror.get("revert_phrases", [])))
        h_colors = horror.get("colors", {})
        for k, btn in self.transform_page.colors.items():
            if k in h_colors:
                btn.set_hex_value(h_colors[k])

        norm_prompts = prompts.get("normal", {})
        for k, edit in self.prompts_page.fields.items():
            if k in norm_prompts:
                edit.setText(norm_prompts[k])

    def build_theme_dict(self) -> Dict[str, Any]:
        theme_id = slugify_theme_id(self.identity_page.id_edit.text())
        display_name = self.identity_page.name_edit.text().strip() or theme_id
        triggers = [t.strip().lower() for t in self.transform_page.triggers_edit.text().split(",") if t.strip()]
        reverts = [r.strip().lower() for r in self.transform_page.reverts_edit.text().split(",") if r.strip()]

        return {
            "id": theme_id,
            "display_name": display_name,
            "version": "1.0.0",
            "plushie": {
                "renderer": "vector_or_sprite",
                "draggable": True,
                "squeezable": True,
                "colors": {k: btn.hex_value() for k, btn in self.normal_page.colors.items()},
                "horror_mode": {
                    "triggers": triggers,
                    "revert_phrases": reverts,
                    "colors": {k: btn.hex_value() for k, btn in self.transform_page.colors.items()},
                },
            },
            "comfort_and_night": {
                "comfort_tint_rgba": [255, 194, 115, 36],
                "night_dim_opacity": 0.80,
                "break_reminder_minutes": 45,
            },
        }

    def build_prompts_dict(self) -> Dict[str, Any]:
        normal_pool = {k: edit.text().strip() for k, edit in self.prompts_page.fields.items()}
        return {
            "normal": normal_pool,
            "horror": dict(normal_pool),
        }

    def accept(self) -> None:
        theme_data = self.build_theme_dict()
        prompts_data = self.build_prompts_dict()
        theme_id = theme_data["id"]

        target_dir = self.root_dir / "themes" / theme_id
        assets_dir = target_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        (target_dir / "theme.json").write_text(json.dumps(theme_data, indent=2), encoding="utf-8")
        (target_dir / "prompts.json").write_text(json.dumps(prompts_data, indent=2), encoding="utf-8")

        sprite_map = {
            "normal_idle.png": self.normal_page.idle_sprite.text().strip(),
            "normal_squeeze.png": self.normal_page.squeeze_sprite.text().strip(),
            "horror_idle.png": self.transform_page.horror_idle_sprite.text().strip(),
            "horror_squeeze.png": self.transform_page.horror_squeeze_sprite.text().strip(),
        }
        for dest_name, src_path in sprite_map.items():
            if src_path and Path(src_path).is_file():
                shutil.copy2(src_path, assets_dir / dest_name)

        if self.identity_page.activate_chk.isChecked():
            settings_path = self.root_dir / "config" / "settings.json"
            if settings_path.exists():
                settings = json.loads(settings_path.read_text(encoding="utf-8"))
                settings["active_theme"] = theme_id
                settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        QMessageBox.information(self, "Theme Saved", f"Saved theme '{theme_data['display_name']}' to themes/{theme_id}/.")
        super().accept()
