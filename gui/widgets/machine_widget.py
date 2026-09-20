#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Виджет конфигурации машины (общий для Decrypt/Machine).
Только отображает/читает конфиг; валидация — в services/EnigmaCore."""
from PySide6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import services


class MachineWidget(QWidget):
    """Панель: модель, роторы, рефлектор, кольца, позиции, штекеры, UKW."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._plugs = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()
        self.model_box = QComboBox()
        for key, meta in services.MACHINE_MODELS.items():
            self.model_box.addItem(meta["label"], key)
        self.model_box.setToolTip("Историческая модель машины")
        form.addRow("Machine", self.model_box)
        lay.addLayout(form)

        self.rotor_row = QHBoxLayout()
        lay.addWidget(QLabel("Rotors (слева направо)"))
        lay.addLayout(self.rotor_row)

        form2 = QFormLayout()
        self.refl_box = QComboBox()
        self.refl_box.setToolTip("Reflector (Umkehrwalze)")
        form2.addRow("Reflector", self.refl_box)
        lay.addLayout(form2)

        self.ring_row = QHBoxLayout()
        self.ring_boxes: list[QSpinBox] = []
        self.pos_row = QHBoxLayout()
        self.pos_boxes: list[QComboBox] = []
        lay.addLayout(self.ring_row)
        lay.addLayout(self.pos_row)

        ukw_lay = QHBoxLayout()
        ukw_lay.addWidget(QLabel("UKW pos/ring (K/D)"))
        self.ukw_pos = QComboBox()
        self.ukw_pos.addItems([chr(c) for c in range(65, 91)])
        self.ukw_ring = QSpinBox()
        self.ukw_ring.setRange(1, 26)
        self.ukw_ring.setToolTip("Кольцо UKW (1=A … 26=Z)")
        ukw_lay.addWidget(self.ukw_pos)
        ukw_lay.addWidget(self.ukw_ring)
        ukw_lay.addStretch(1)
        self.ukw_wrap = QWidget()
        self.ukw_wrap.setLayout(ukw_lay)
        lay.addWidget(self.ukw_wrap)

        plug_box = QGroupBox("Plugboard")
        plug_lay = QVBoxLayout(plug_box)
        self.plug_label = QLabel("—")
        self.plug_label.setObjectName("mono")
        plug_lay.addWidget(self.plug_label)
        self.plug_btn = QPushButton("Edit Plugboard")
        self.plug_btn.setObjectName("secondary")
        plug_lay.addWidget(self.plug_btn)
        lay.addWidget(plug_box)
        lay.addStretch(1)

        self.rotor_boxes: list[QComboBox] = []
        self.model_box.currentIndexChanged.connect(self._rebuild)
        self.plug_btn.clicked.connect(self._edit_plugs)
        self.model_box.setCurrentIndex(list(services.MACHINE_MODELS).index("M3"))

    def _rebuild(self):
        model = self.model_box.currentData()
        meta = services.MACHINE_MODELS[model]
        # роторы
        while self.rotor_row.count():
            w = self.rotor_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.rotor_boxes = []
        for opts in meta["rotors"]:
            box = QComboBox()
            box.addItems(opts)
            self.rotor_row.addWidget(box)
            self.rotor_boxes.append(box)
        # рефлектор
        self.refl_box.clear()
        self.refl_box.addItems(meta["reflectors"])
        self.refl_box.setEnabled(bool(meta["reflectors"]))
        # кольца/позиции: количество из MachineSpec (у G 4: [UKW,L,M,R],
        # первый бокс — UKW). Значения по умолчанию — без дублей колёс.
        is_g = model in ("G", "G312", "G260")
        while self.ring_row.count():
            w = self.ring_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.ring_boxes = []
        self.ring_row.addWidget(QLabel("Ring settings"
                                       + (" [UKW,L,M,R]" if is_g else "")))
        for i in range(meta["rings"]):
            sp = QSpinBox()
            sp.setRange(1, 26)
            sp.setToolTip("Кольцо UKW (1=A … 26=Z)" if is_g and i == 0
                          else "Кольцо (1=A … 26=Z)")
            self.ring_row.addWidget(sp)
            self.ring_boxes.append(sp)
        self.ring_row.addStretch(1)
        # позиции
        while self.pos_row.count():
            w = self.pos_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.pos_boxes = []
        self.pos_row.addWidget(QLabel("Initial positions"
                                      + (" [UKW,L,M,R]" if is_g else "")))
        for i in range(meta["positions"]):
            box = QComboBox()
            box.addItems([chr(c) for c in range(65, 91)])
            box.setToolTip("Стартовая позиция UKW" if is_g and i == 0
                           else "Стартовая позиция ротора")
            self.pos_row.addWidget(box)
            self.pos_boxes.append(box)
        self.pos_row.addStretch(1)
        # дефолтные колёса без дублей (из MachineSpec)
        for box, name in zip(self.rotor_boxes,
                             services.default_config(model)["rotors"]):
            j = box.findText(name)
            if j >= 0:
                box.setCurrentIndex(j)
        self.ukw_wrap.setVisible(bool(meta["ukw"]))
        self.plug_btn.setEnabled(meta["plugs"])
        if not meta["plugs"]:
            self._plugs = ""
            self._refresh_plug_label()

    def _edit_plugs(self):
        from gui.dialogs.plugboard_dialog import PlugboardDialog
        dlg = PlugboardDialog(self._plugs, self)
        if dlg.exec():
            self._plugs = dlg.pairs()
            self._refresh_plug_label()

    def _refresh_plug_label(self):
        n = len(self._plugs.split()) if self._plugs else 0
        self.plug_label.setText((self._plugs or "—") + f"   ({n}/10)")

    def get_config(self) -> dict:
        model = self.model_box.currentData()
        n = len(self.rotor_boxes)
        to_letters = "".join(chr(64 + b.value()) for b in self.ring_boxes)
        return {"model": model,
                "rotors": [b.currentText() for b in self.rotor_boxes],
                "reflector": self.refl_box.currentText() if self.refl_box.count() else "B",
                "rings": to_letters if n > 0 else "A" * n,
                "positions": "".join(b.currentText() for b in self.pos_boxes),
                "plugs": self._plugs,
                "ukw_pos": self.ukw_pos.currentText(),
                "ukw_ring": chr(64 + self.ukw_ring.value())}

    def set_config(self, cfg: dict):
        meta = services.MACHINE_MODELS.get(cfg.get("model", "M3"))
        if meta is None:
            return
        self.model_box.setCurrentIndex(list(services.MACHINE_MODELS).index(cfg["model"]))
        self._rebuild()
        for box, name in zip(self.rotor_boxes, cfg.get("rotors", [])):
            i = box.findText(name)
            if i >= 0:
                box.setCurrentIndex(i)
        if self.refl_box.count() and cfg.get("reflector"):
            i = self.refl_box.findText(cfg["reflector"])
            if i >= 0:
                self.refl_box.setCurrentIndex(i)
        rings = cfg.get("rings", "")
        for box, ch in zip(self.ring_boxes, rings):
            if "A" <= ch <= "Z":
                box.setValue(ord(ch) - 64)
        for box, ch in zip(self.pos_boxes, cfg.get("positions", "")):
            i = box.findText(ch)
            if i >= 0:
                box.setCurrentIndex(i)
        self._plugs = cfg.get("plugs", "")
        self._refresh_plug_label()
        if cfg.get("ukw_pos"):
            i = self.ukw_pos.findText(cfg["ukw_pos"])
            if i >= 0:
                self.ukw_pos.setCurrentIndex(i)
        if cfg.get("ukw_ring") and len(cfg["ukw_ring"]) == 1:
            self.ukw_ring.setValue(ord(cfg["ukw_ring"]) - 64)
