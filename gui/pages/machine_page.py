#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Machine: диагностика состояния + пошаговый тест (double-step)."""
import logging

from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import services
from gui.widgets.machine_widget import MachineWidget

log = logging.getLogger("enigma_gui")


class MachinePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._machine = None
        self._cfg: dict = {}
        lay = QVBoxLayout(self)
        title = QLabel("Machine state")
        title.setObjectName("title")
        lay.addWidget(title)

        top = QHBoxLayout()
        self.cfg = MachineWidget()
        top.addWidget(self.cfg, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Состояние роторов"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Rotor", "Position", "Ring", "Notch"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        right.addWidget(self.table)
        self.refl_label = QLabel("Reflector: —")
        self.plug_label = QLabel("Plugboard: —")
        right.addWidget(self.refl_label)
        right.addWidget(self.plug_label)
        top.addLayout(right, 1)
        lay.addLayout(top)

        test = QGridLayout()
        test.addWidget(QLabel("Input"), 0, 0)
        self.inp = QLineEdit()
        self.inp.setObjectName("mono")
        self.inp.setPlaceholderText("HELLOWORLD")
        test.addWidget(self.inp, 0, 1)
        test.addWidget(QLabel("Output"), 1, 0)
        self.out = QLineEdit()
        self.out.setObjectName("mono")
        self.out.setReadOnly(True)
        test.addWidget(self.out, 1, 1)
        lay.addLayout(test)

        row = QHBoxLayout()
        self.build_btn = QPushButton("Build / Reset")
        self.build_btn.setToolTip("Построить машину из конфигурации выше")
        self.step_btn = QPushButton("Step")
        self.step_btn.setObjectName("secondary")
        self.step_btn.setToolTip("Обработать один символ и показать сдвиг роторов")
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("secondary")
        for b in (self.build_btn, self.step_btn, self.reset_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

        self.build_btn.clicked.connect(self._build)
        self.step_btn.clicked.connect(self._step)
        self.reset_btn.clicked.connect(self._build)

    def _build(self):
        try:
            cfg = self.cfg.get_config()
            self._machine = services.build_machine(cfg)
            self._cfg = cfg
        except ValueError as ex:
            QMessageBox.warning(self, "Неверная конфигурация", str(ex))
            return
        self.out.clear()
        self._refresh()

    def _refresh(self):
        if self._machine is None:
            return
        m = self._machine
        rows = [(r.name, chr(65 + r.pos), str(r.ring + 1),
                 "".join(chr(65 + n) for n in sorted(r._notches)) or "—")
                for r in m.rotors]
        if hasattr(m, "ukw"):
            rows.insert(0, ("UKW", chr(65 + m.ukw.pos), str(m.ukw.ring + 1), "—"))
        self.table.setRowCount(len(rows))
        for i, (a, b, c, d) in enumerate(rows):
            for j, v in enumerate((a, b, c, d)):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.refl_label.setText(
            "Reflector: " + getattr(m, "reflector_name", getattr(m, "model", "?")))
        self.plug_label.setText("Plugboard: " + (self._cfg.get("plugs") or "—"))

    def _step(self):
        if self._machine is None:
            self._build()
            if self._machine is None:
                return
        text = "".join(c for c in self.inp.text().upper() if "A" <= c <= "Z")
        if not text:
            QMessageBox.information(self, "Step", "Введите хотя бы одну букву A–Z.")
            return
        try:
            out = self._machine.press(text[0])
        except Exception:  # noqa: BLE001
            log.exception("step error")
            QMessageBox.warning(self, "Step", "Не удалось обработать символ. См. лог.")
            return
        self.out.setText(self.out.text() + out)
        self.inp.setText(text[1:])
        self._refresh()

    def on_run(self):
        self._build()
