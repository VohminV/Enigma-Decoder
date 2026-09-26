#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Historical Keys: поиск по базе, детали, редактор записей."""
import logging
import os
import shutil

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import services

log = logging.getLogger("enigma_gui")


class EntryDialog(QDialog):
    """Редактор записи ключа (валидация через построение машины)."""

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit key entry")
        self._entry = entry
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.f_date = QLineEdit(entry.get("date", ""))
        self.f_model = QComboBox()
        self.f_model.addItems(list(services.MACHINE_MODELS))
        self.f_model.setCurrentText(entry.get("model", "M3"))
        self.f_rotors = QLineEdit(" ".join(entry.get("wheels", [])))
        self.f_greek = QLineEdit(entry.get("greek") or "")
        self.f_refl = QLineEdit(entry.get("reflector") or "")
        self.f_rings = QLineEdit(entry.get("rings", ""))
        self.f_plugs = QLineEdit(entry.get("plugs", ""))
        self.f_status = QComboBox()
        self.f_status.addItems(["verified", "published"])
        self.f_status.setCurrentText(entry.get("status", "published"))
        self.f_notes = QTextEdit(entry.get("notes", ""))
        self.f_notes.setMaximumHeight(80)
        for label, w in (("Date (YYYY-MM-DD)", self.f_date), ("Model", self.f_model),
                         ("Rotors (space separated)", self.f_rotors),
                         ("Greek (M4)", self.f_greek), ("Reflector", self.f_refl),
                         ("Rings", self.f_rings), ("Plugboard", self.f_plugs),
                         ("Status", self.f_status), ("Notes", self.f_notes)):
            form.addRow(label, w)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._save_check)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _save_check(self):
        try:
            import keydb
            from enigma import spec_for
            model = self.f_model.currentText()
            spec = spec_for(model)
            wheels = self.f_rotors.text().split()
            cfg = {"model": model,
                   "rotors": (([self.f_greek.text().strip() or "Beta"]
                               if model == "M4" else []) + wheels),
                   "reflector": self.f_refl.text().strip() or "B",
                   "rings": self.f_rings.text().strip() or "A" * spec.rings,
                   "positions": "A" * spec.positions,
                   "plugs": self.f_plugs.text().strip(),
                   "ukw_pos": "A", "ukw_ring": "A"}
            services.build_machine(cfg)
            candidate = self.result_entry()
            errs = keydb.validate_entry(candidate)
            if errs:
                QMessageBox.warning(self, "Проверка",
                                    "Запись невалидна:\n" + "\n".join(errs[:6]))
                return
        except ValueError as ex:
            QMessageBox.warning(self, "Проверка", f"Конфигурация невалидна: {ex}")
            return
        self.accept()

    def result_entry(self) -> dict:
        e = dict(self._entry)
        e.update({"date": self.f_date.text().strip(),
                  "model": self.f_model.currentText(),
                  "wheels": self.f_rotors.text().split(),
                  "greek": self.f_greek.text().strip() or None,
                  "reflector": self.f_refl.text().strip(),
                  "rings": self.f_rings.text().strip(),
                  "plugs": self.f_plugs.text().strip(),
                  "status": self.f_status.currentText(),
                  "notes": self.f_notes.toPlainText()})
        return e


class KeysPage(QWidget):
    request_apply = None  # callback(config)
    request_decrypt = None  # callback(config, cipher)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[dict] = []
        self._rows: list[dict] = []
        self._db_path: str | None = None
        lay = QVBoxLayout(self)
        title = QLabel("Historical Keys")
        title.setObjectName("title")
        lay.addWidget(title)

        filt = QHBoxLayout()
        filt.addWidget(QLabel("Date from"))
        self.d_from = QLineEdit("1940-01-01")
        self.d_from.setMaximumWidth(110)
        filt.addWidget(self.d_from)
        filt.addWidget(QLabel("to"))
        self.d_to = QLineEdit("1945-12-31")
        self.d_to.setMaximumWidth(110)
        filt.addWidget(self.d_to)
        filt.addWidget(QLabel("Machine"))
        self.machine = QComboBox()
        self.machine.addItems(["All", "I", "M3", "M4", "G", "G312", "G260", "K", "D"])
        filt.addWidget(self.machine)
        self.search_btn = QPushButton("Search")
        self.import_btn = QPushButton("Import")
        self.import_btn.setObjectName("secondary")
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("secondary")
        filt.addWidget(self.search_btn)
        filt.addWidget(self.import_btn)
        filt.addWidget(self.export_btn)
        filt.addStretch(1)
        lay.addLayout(filt)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Machine", "Rotors", "Reflector", "Rings", "Plugboard"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._details)
        lay.addWidget(self.table, 1)

        self.detail = QTextEdit()
        self.detail.setObjectName("mono")
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(150)
        lay.addWidget(self.detail)

        row = QHBoxLayout()
        self.use_btn = QPushButton("Use Configuration")
        self.use_btn.setToolTip("Отправить ключ на страницу Decrypt")
        self.decrypt_btn = QPushButton("Decrypt")
        self.decrypt_btn.setObjectName("secondary")
        self.decrypt_btn.setToolTip("Расшифровать первое сообщение записи")
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("secondary")
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("secondary")
        for b in (self.use_btn, self.decrypt_btn, self.copy_btn, self.edit_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)

        self.search_btn.clicked.connect(self.search)
        self.import_btn.clicked.connect(self._import)
        self.export_btn.clicked.connect(self._export)
        self.use_btn.clicked.connect(self._use)
        self.decrypt_btn.clicked.connect(self._decrypt_first)
        self.copy_btn.clicked.connect(self._copy)
        self.edit_btn.clicked.connect(self._edit)
        self.search()

    def _load(self, path=None):
        if path is None:
            # R-06: путь из Settings используется как дефолт, если файл есть.
            try:
                from PySide6.QtCore import QSettings
                configured = (QSettings("EnigmaDecoder", "enigma").value(
                    "dbpath", "") or "").strip()
                if configured and os.path.exists(configured):
                    path = configured
            except Exception:  # noqa: BLE001
                path = None
        try:
            self._entries = services.db_entries(path)
            if path:
                self._db_path = path
        except Exception as ex:  # noqa: BLE001
            log.exception("db load failed")
            QMessageBox.critical(self, "База ключей",
                                 f"Unable to load historical key database.\n\nDetails:\n{ex}")
            self._entries = []

    def search(self):
        self._load(self._db_path)
        rows = services.search_entries(self._entries, self.d_from.text().strip(),
                                       self.d_to.text().strip(),
                                       self.machine.currentText())
        self._rows = rows
        self.table.setRowCount(0)
        for e in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            wheels = " ".join(filter(None, [e.get("greek")] + list(e["wheels"])))
            for j, v in enumerate((e["date"], e["model"], wheels,
                                   e.get("reflector", ""), e.get("rings", ""),
                                   e.get("plugs", ""))):
                self.table.setItem(r, j, QTableWidgetItem(v))
        self.detail.clear()

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self._rows:
            return None
        return self._rows[rows[0].row()]

    def _default_db_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(services.__file__)),
                            "keys.json")

    def _edit_target(self):
        """(path, is_copy): куда сохранять правку (AUD-007).

        Импортированный внешний файл — read-only источник: правим локальную
        копию (user override), оригинал не трогаем. Собственная база —
        правим на месте (атомарно, см. keydb.atomic_write_json).
        """
        if self._db_path and (os.path.abspath(self._db_path)
                              != os.path.abspath(self._default_db_path())):
            return self._default_db_path(), True
        return self._db_path or self._default_db_path(), False

    def _details(self):
        e = self._selected()
        if not e:
            return
        lines = [f"{e['id']}  ({e['date']}, {e['service']})",
                 f"Model: {e['model']}, reflector: {e.get('reflector')}, "
                 f"greek: {e.get('greek')}, wheels: {' '.join(e['wheels'])}",
                 f"Rings: {e['rings']}" +
                 (f" (also: {', '.join(e.get('rings_alt', []))})" if e.get("rings_alt") else ""),
                 f"Plugs: {e.get('plugs') or '—'}", f"Status: {e['status']}"]
        for m in e.get("messages", []):
            lines.append(f"  msg {m['id']}: key={m.get('key')} verified={m.get('verified')}")
        if e.get("notes"):
            lines.append("Notes: " + e["notes"])
        self.detail.setPlainText("\n".join(lines))

    def _first_cipher_msg(self, e):
        for m in e.get("messages", []):
            if m.get("cipher") and m.get("key"):
                return m
        return None

    def _use(self):
        e = self._selected()
        m = self._first_cipher_msg(e) if e else None
        if not e or not callable(self.request_apply):
            return
        key = m["key"] if m else "A" * (len(e["wheels"]) + (1 if e.get("greek") else 0))
        self.request_apply(services.entry_machine_config(e, key))

    def _decrypt_first(self):
        e = self._selected()
        m = self._first_cipher_msg(e) if e else None
        if not m or not callable(self.request_decrypt):
            if e and not m:
                QMessageBox.information(self, "Decrypt",
                                        "У этой записи нет сообщения с шифротекстом.")
            return
        self.request_decrypt(services.entry_machine_config(e, m["key"]), m["cipher"])

    def _copy(self):
        e = self._selected()
        if e:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(
                f"{e['date']} {e['model']} {' '.join(e['wheels'])} "
                f"{e.get('reflector')} {e['rings']} {e.get('plugs')}")

    def _edit(self):
        e = self._selected()
        if not e:
            return
        dlg = EntryDialog(e, self)
        if not dlg.exec():
            return
        new_entry = dlg.result_entry()
        for i, old in enumerate(self._entries):
            if old["id"] == e["id"]:
                self._entries[i] = new_entry
                break
        import keydb
        path, is_copy = self._edit_target()
        try:
            if os.path.exists(path):
                shutil.copy(path, path + ".bak")
            keydb.atomic_write_json(
                path, {"version": 1, "entries": self._entries})
        except OSError as ex:
            QMessageBox.critical(self, "Сохранение", f"Не могу записать: {ex}")
            return
        if is_copy:
            QMessageBox.information(
                self, "Сохранение",
                "Импортированный файл оставлен без изменений.\n"
                f"Правка сохранена в локальную копию:\n{path}")
            self._db_path = None
        self.search()

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import key database",
                                              "", "JSON (*.json)")
        if not path:
            return
        try:
            data = services.db_entries(path)
            if not isinstance(data, list):
                raise ValueError("bad format")
            import keydb
            bad = keydb.validate_db(data)
            if bad:
                lines = []
                for eid, errs in list(bad.items())[:5]:
                    lines.append(f"{eid}: {errs[0]}")
                extra = f" (+{len(bad) - 5} more)" if len(bad) > 5 else ""
                raise ValueError(
                    f"Некорректные записи ({len(bad)}):\n"
                    + "\n".join(lines) + extra)
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Import", f"Некорректный файл: {ex}")
            return
        self._db_path = path
        self.search()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export key database",
                                              "keys_export.json", "JSON (*.json)")
        if not path:
            return
        try:
            import keydb
            keydb.atomic_write_json(
                path, {"version": 1, "entries": self._entries})
        except OSError as ex:
            QMessageBox.critical(self, "Export", f"Не могу записать: {ex}")
