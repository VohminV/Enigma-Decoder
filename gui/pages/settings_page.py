#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Settings: тема, потоки, база, лог. Хранение — QSettings."""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)


class SettingsPage(QWidget):
    theme_changed = None  # callback(name) — задаёт главное окно

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qs = QSettings("EnigmaDecoder", "enigma")
        lay = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("title")
        lay.addWidget(title)
        form = QFormLayout()

        self.theme = QComboBox()
        self.theme.addItems(["Dark", "System"])
        self.theme.setCurrentText(self.qs.value("theme", "Dark"))
        self.theme.currentTextChanged.connect(self._theme)
        form.addRow("Theme", self.theme)

        self.lang = QComboBox()
        self.lang.addItems(["English"])
        self.lang.setToolTip("Другие языки пока не поддерживаются")
        form.addRow("Language", self.lang)

        self.threads = QSpinBox()
        self.threads.setRange(0, 64)
        self.threads.setSpecialValueText("Auto")
        self.threads.setValue(int(self.qs.value("threads", 0)))
        self.threads.setToolTip("Использоваться будет worker-пулом cracker (Phase 7+)")
        self.threads.valueChanged.connect(
            lambda v: self.qs.setValue("threads", v))
        form.addRow("Worker threads", self.threads)

        dbrow = QHBoxLayout()
        self.dbpath = QLineEdit(self.qs.value("dbpath", ""))
        self.dbpath.setPlaceholderText("По умолчанию: keys.json рядом с программой")
        self.dbpath.editingFinished.connect(
            lambda: self.qs.setValue("dbpath", self.dbpath.text()))
        browse = QPushButton("Browse")
        browse.setObjectName("secondary")
        browse.clicked.connect(self._browse)
        dbrow.addWidget(self.dbpath, 1)
        dbrow.addWidget(browse)
        form.addRow("Database", dbrow)

        self.loglevel = QComboBox()
        self.loglevel.addItems(["Normal", "Debug"])
        self.loglevel.setCurrentText(self.qs.value("loglevel", "Normal"))
        form.addRow("Log level", self.loglevel)

        self.ocr_engine = QComboBox()
        self.ocr_engine.addItems(["RapidOCR PP-OCRv6 (ONNX CPU)"])
        self.ocr_engine.setToolTip("Единственный встроенный движок; 100% offline")
        form.addRow("OCR Engine", self.ocr_engine)

        try:
            import torch
            cuda = torch.cuda.is_available()
        except ImportError:
            cuda = False
        self.ocr_device = QComboBox()
        self.ocr_device.addItems(["CPU"])
        self.ocr_device.setToolTip("Движок работает на CPU (onnxruntime)" +
                                   ("; CUDA есть в системе, GPU-бэкенд — позже"
                                    if cuda else ""))
        form.addRow("OCR Device", self.ocr_device)

        self.ocr_profile = QComboBox()
        self.ocr_profile.addItems(["Ciphertext", "Document", "Typewritten",
                                   "Historical Scan", "Photograph",
                                   "High Contrast", "Original"])
        self.ocr_profile.setCurrentText(self.qs.value("ocr_profile", "Ciphertext"))
        self.ocr_profile.currentTextChanged.connect(
            lambda v: self.qs.setValue("ocr_profile", v))
        form.addRow("Default OCR profile", self.ocr_profile)

        self.ocr_policy = QComboBox()
        self.ocr_policy.addItems(["Conservative", "Balanced", "Aggressive"])
        self.ocr_policy.setCurrentText(self.qs.value("ocr_policy", "Conservative"))
        self.ocr_policy.currentTextChanged.connect(
            lambda v: self.qs.setValue("ocr_policy", v))
        form.addRow("Default correction policy", self.ocr_policy)
        lay.addLayout(form)
        lay.addStretch(1)

    def _theme(self, name):
        self.qs.setValue("theme", name)
        if callable(self.theme_changed):
            self.theme_changed(name)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Key database", "",
                                              "JSON (*.json)")
        if path:
            self.dbpath.setText(path)
            self.qs.setValue("dbpath", path)
