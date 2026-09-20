#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Decrypt: ручная шифровка/расшифровка через EnigmaCore."""
import logging

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSplitter, QTextEdit, QVBoxLayout, QWidget)

import services
from gui.widgets.machine_widget import MachineWidget

log = logging.getLogger("enigma_gui")


class DecryptPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        title = QLabel("Decrypt / Encrypt")
        title.setObjectName("title")
        lay.addWidget(title)

        split = QSplitter()
        self.cipher = QTextEdit()
        self.cipher.setObjectName("mono")
        self.cipher.setPlaceholderText("CIPHERTEXT — вставьте шифротекст…")
        self.plain = QTextEdit()
        self.plain.setObjectName("mono")
        self.plain.setPlaceholderText("PLAINTEXT — результат…")
        split.addWidget(self._wrap("CIPHERTEXT", self.cipher))
        split.addWidget(self._wrap("PLAINTEXT", self.plain))
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        btns = QHBoxLayout()
        self.decrypt_btn = QPushButton("Decrypt")
        self.decrypt_btn.setToolTip("Расшифровать (Ctrl+Enter)")
        self.encrypt_btn = QPushButton("Encrypt")
        self.encrypt_btn.setObjectName("secondary")
        self.encrypt_btn.setToolTip("Зашифровать (те же настройки)")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondary")
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("secondary")
        self.paste_btn = QPushButton("Paste")
        self.paste_btn.setObjectName("secondary")
        for b in (self.decrypt_btn, self.encrypt_btn, self.clear_btn,
                  self.copy_btn, self.paste_btn):
            btns.addWidget(b)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.machine = MachineWidget()
        lay.addWidget(self.machine)

        self.decrypt_btn.clicked.connect(lambda: self._run(from_cipher=True))
        self.encrypt_btn.clicked.connect(lambda: self._run(from_cipher=False))
        self.clear_btn.clicked.connect(self._clear)
        self.copy_btn.clicked.connect(
            lambda: self._to_clipboard(self.plain.toPlainText()))
        self.paste_btn.clicked.connect(
            lambda: self.cipher.setPlainText(self._from_clipboard()))

    def _wrap(self, title, widget):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(title)
        lab.setObjectName("muted")
        lay.addWidget(lab)
        lay.addWidget(widget)
        return w

    def _to_clipboard(self, text):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)

    def _from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        return QApplication.clipboard().text()

    def _clear(self):
        self.cipher.clear()
        self.plain.clear()

    def _run(self, from_cipher: bool):
        src = self.cipher.toPlainText() if from_cipher else self.plain.toPlainText()
        if not src.strip():
            return
        try:
            cfg = self.machine.get_config()
            out = services.process_text(cfg, src)
        except ValueError as ex:
            log.warning("decrypt failed: %s", ex)
            QMessageBox.warning(self, "Неверная конфигурация", str(ex))
            return
        except Exception:  # noqa: BLE001
            log.exception("decrypt error")
            QMessageBox.critical(self, "Ошибка", "Неожиданная ошибка, подробности в логе.")
            return
        if from_cipher:
            self.plain.setPlainText(out)
        else:
            self.cipher.setPlainText(out)

    # для шорткатов главного окна
    def on_run(self):
        self._run(from_cipher=True)
