#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Главное окно: sidebar + страницы + статусбар + шорткаты."""
import logging

from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QStatusBar, QVBoxLayout, QWidget)

from gui.pages.benchmark_page import BenchmarkPage
from gui.pages.crack_page import CrackPage
from gui.pages.decrypt_page import DecryptPage
from gui.pages.keys_page import KeysPage
from gui.pages.machine_page import MachinePage
from gui.pages.ocr_page import OCRPage
from gui.pages.settings_page import SettingsPage
from gui.styles import DARK_QSS

log = logging.getLogger("enigma_gui")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ENIGMA DECODER")
        self.resize(1180, 760)
        self.qs = QSettings("EnigmaDecoder", "enigma")

        root = QWidget()
        lay = QHBoxLayout(root)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        side = QVBoxLayout()
        head = QLabel("ENIGMA\nDECODER")
        head.setObjectName("title")
        side.addWidget(head)
        self.nav_btns: dict[str, QPushButton] = {}
        self.pages = QStackedWidget()
        self._page_index: dict[str, int] = {}
        for name, cls in (("Decrypt", DecryptPage), ("Crack", CrackPage),
                          ("OCR", OCRPage), ("Keys", KeysPage),
                          ("Machine", MachinePage),
                          ("Benchmark", BenchmarkPage), ("Settings", SettingsPage)):
            btn = QPushButton(name)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, n=name: self.goto(n))
            side.addWidget(btn)
            self.nav_btns[name] = btn
            page = cls()
            self._page_index[name] = self.pages.addWidget(page)
        side.addStretch(1)
        side_wrap = QWidget()
        side_wrap.setLayout(side)
        side_wrap.setFixedWidth(190)
        lay.addWidget(side_wrap)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.status_label = QLabel("Ready")
        self.worker_label = QLabel("")
        status.addWidget(self.status_label, 1)
        status.addWidget(self.worker_label)
        self.setStatusBar(status)

        # межстраничные связи (через application state, не clipboard)
        keys = self.page("Keys")
        keys.request_apply = self.apply_config_to_decrypt
        keys.request_decrypt = self.decrypt_with_config
        crack = self.page("Crack")
        crack.request_apply = self.apply_config_to_decrypt
        ocr = self.page("OCR")
        ocr.request_decrypt_text = self.ocr_to_decrypt
        ocr.request_crack_text = self.ocr_to_crack
        settings = self.page("Settings")
        settings.theme_changed = self.apply_theme

        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._run_current)
        QShortcut(QKeySequence("Ctrl+Enter"), self).activated.connect(self._run_current)
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._stop_current)

        self.apply_theme(self.qs.value("theme", "Dark"))
        self.goto("Decrypt")

    def page(self, name):
        return self.pages.widget(self._page_index[name])

    def goto(self, name):
        self.pages.setCurrentIndex(self._page_index[name])
        for n, b in self.nav_btns.items():
            b.setChecked(n == name)
        self.status_label.setText(f"Ready — {name}")

    def apply_config_to_decrypt(self, cfg: dict):
        self.page("Decrypt").machine.set_config(cfg)
        self.goto("Decrypt")
        self.status_label.setText("Configuration applied to Decrypt")

    def decrypt_with_config(self, cfg: dict, cipher: str):
        dec = self.page("Decrypt")
        dec.machine.set_config(cfg)
        dec.cipher.setPlainText(cipher)
        self.goto("Decrypt")
        dec.on_run()

    def ocr_to_decrypt(self, text: str):
        dec = self.page("Decrypt")
        dec.cipher.setPlainText(text)
        self.goto("Decrypt")
        dec.on_run()
        self.status_label.setText("OCR text sent to Decrypt")

    def ocr_to_crack(self, text: str):
        crack = self.page("Crack")
        crack.set_custom_cipher(text)
        self.goto("Crack")
        self.status_label.setText("OCR text set as custom ciphertext in Crack")

    def apply_theme(self, name):
        self.setStyleSheet(DARK_QSS if name == "Dark" else "")

    def _run_current(self):
        page = self.pages.currentWidget()
        if hasattr(page, "on_run"):
            page.on_run()

    def _stop_current(self):
        page = self.pages.currentWidget()
        if hasattr(page, "on_stop"):
            page.on_stop()

    def closeEvent(self, event):
        # Остановка всех worker'ов: отмена + ограниченное ожидание
        # (не блокируем закрытие навсегда).
        for name in ("Crack", "OCR", "Benchmark"):
            page = self.page(name)
            if hasattr(page, "on_stop"):
                try:
                    page.on_stop()
                except Exception:  # noqa: BLE001
                    log.exception("stop %s failed", name)
        for name in ("Crack", "OCR", "Benchmark"):
            worker = getattr(self.page(name), "_worker", None)
            if worker is not None:
                worker.wait(3000)
        super().closeEvent(event)
