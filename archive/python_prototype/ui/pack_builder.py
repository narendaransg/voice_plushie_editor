import json
from pathlib import Path
from typing import Dict, Any

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QComboBox,
    QListWidget,
    QLineEdit,
    QCheckBox,
    QPushButton,
    QLabel,
    QMessageBox,
)


class PackBuilderDialog(QDialog):
    """Editor for per-app JSON command packs (aliases, keys, supported flag, refusal reason)."""

    def __init__(self, root_dir: Path, parent=None):
        super().__init__(parent)
        self.root_dir = Path(root_dir)
        self.profiles_dir = self.root_dir / "config" / "profiles"
        self.setWindowTitle("Command Pack Builder")
        self.resize(640, 440)

        self.current_profile_key: str = ""
        self.current_data: Dict[str, Any] = {}

        self._build_ui()
        self._load_profile_list()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("App Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        top_row.addWidget(self.profile_combo, stretch=1)

        self.save_btn = QPushButton("Save Profile")
        self.save_btn.clicked.connect(self._save_profile)
        top_row.addWidget(self.save_btn)
        root_layout.addLayout(top_row)

        mid_row = QHBoxLayout()

        left_col = QVBoxLayout()
        self.cmd_list = QListWidget()
        self.cmd_list.currentTextChanged.connect(self._on_command_selected)
        left_col.addWidget(self.cmd_list)

        add_row = QHBoxLayout()
        self.new_cmd_edit = QLineEdit()
        self.new_cmd_edit.setPlaceholderText("new_command_name")
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_command)
        del_btn = QPushButton("Remove")
        del_btn.clicked.connect(self._remove_command)
        add_row.addWidget(self.new_cmd_edit)
        add_row.addWidget(add_btn)
        add_row.addWidget(del_btn)
        left_col.addLayout(add_row)
        mid_row.addLayout(left_col, stretch=1)

        form = QFormLayout()
        self.aliases_edit = QLineEdit()
        self.aliases_edit.setPlaceholderText("split, cut, blade")
        self.keys_edit = QLineEdit()
        self.keys_edit.setPlaceholderText("ctrl, b")
        self.supported_chk = QCheckBox("Supported by automation")
        self.confirm_chk = QCheckBox("Require confirmation before running")
        self.reason_edit = QLineEdit()
        self.reason_edit.setPlaceholderText("Reason shown when unsupported")

        self.aliases_edit.editingFinished.connect(self._sync_form_to_data)
        self.keys_edit.editingFinished.connect(self._sync_form_to_data)
        self.supported_chk.stateChanged.connect(self._sync_form_to_data)
        self.confirm_chk.stateChanged.connect(self._sync_form_to_data)
        self.reason_edit.editingFinished.connect(self._sync_form_to_data)

        form.addRow("Spoken Aliases:", self.aliases_edit)
        form.addRow("Key Combo:", self.keys_edit)
        form.addRow("", self.supported_chk)
        form.addRow("", self.confirm_chk)
        form.addRow("Refusal Reason:", self.reason_edit)
        mid_row.addLayout(form, stretch=2)

        root_layout.addLayout(mid_row)

    def _load_profile_list(self) -> None:
        self.profile_combo.clear()
        if not self.profiles_dir.exists():
            return
        for p in sorted(self.profiles_dir.glob("*.json")):
            self.profile_combo.addItem(p.stem, p.stem)

    def _on_profile_changed(self) -> None:
        key = self.profile_combo.currentData()
        if not key:
            return
        self.current_profile_key = key
        path = self.profiles_dir / f"{key}.json"
        self.current_data = json.loads(path.read_text(encoding="utf-8"))
        self.cmd_list.clear()
        for cmd_name in self.current_data.get("commands", {}).keys():
            self.cmd_list.addItem(cmd_name)
        if self.cmd_list.count() > 0:
            self.cmd_list.setCurrentRow(0)

    def _on_command_selected(self, cmd_name: str) -> None:
        if not cmd_name:
            return
        cmd_cfg = self.current_data.get("commands", {}).get(cmd_name, {})
        self.aliases_edit.setText(", ".join(cmd_cfg.get("aliases", [])))
        self.keys_edit.setText(", ".join(cmd_cfg.get("keys", [])))
        self.supported_chk.setChecked(bool(cmd_cfg.get("supported", True)))
        self.confirm_chk.setChecked(bool(cmd_cfg.get("requires_confirm", False)))
        self.reason_edit.setText(cmd_cfg.get("reason", ""))

    def _sync_form_to_data(self) -> None:
        item = self.cmd_list.currentItem()
        if not item:
            return
        cmd_name = item.text()
        cmds = self.current_data.setdefault("commands", {})
        entry: Dict[str, Any] = {
            "aliases": [a.strip() for a in self.aliases_edit.text().split(",") if a.strip()],
            "keys": [k.strip() for k in self.keys_edit.text().split(",") if k.strip()],
            "supported": self.supported_chk.isChecked(),
        }
        if self.confirm_chk.isChecked():
            entry["requires_confirm"] = True
        reason = self.reason_edit.text().strip()
        if reason:
            entry["reason"] = reason
        cmds[cmd_name] = entry

    def _add_command(self) -> None:
        name = self.new_cmd_edit.text().strip().lower().replace(" ", "_")
        if not name:
            return
        cmds = self.current_data.setdefault("commands", {})
        if name not in cmds:
            cmds[name] = {"aliases": [name.replace("_", " ")], "keys": [], "supported": True}
            self.cmd_list.addItem(name)
        self.new_cmd_edit.clear()
        self.cmd_list.setCurrentRow(self.cmd_list.count() - 1)

    def _remove_command(self) -> None:
        row = self.cmd_list.currentRow()
        if row < 0:
            return
        item = self.cmd_list.takeItem(row)
        if item:
            self.current_data.get("commands", {}).pop(item.text(), None)

    def _save_profile(self) -> None:
        self._sync_form_to_data()
        if not self.current_profile_key:
            return
        path = self.profiles_dir / f"{self.current_profile_key}.json"
        path.write_text(json.dumps(self.current_data, indent=2), encoding="utf-8")
        QMessageBox.information(self, "Saved", f"Saved {path.name}.")
