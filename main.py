#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точка входа GUI: python main.py (из каталога D:\\enigma)."""
import logging
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "enigma_gui.log")


LOG_LEVELS = {"Normal": logging.INFO, "Debug": logging.DEBUG}


def loglevel_to_level(name: str) -> int:
    """QSettings-значение Settings → уровень logging. R-06: подключено."""
    return LOG_LEVELS.get((name or "").strip(), logging.INFO)


def _setup_logging() -> None:
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    try:
        from PySide6.QtCore import QSettings
        level = loglevel_to_level(QSettings("EnigmaDecoder", "enigma").value(
            "loglevel", "Normal"))
    except Exception:  # noqa: BLE001 — PySide6 нет: дефолт INFO
        level = logging.INFO
    root.setLevel(level)
    root.addHandler(handler)


def main() -> int:
    _setup_logging()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print("PySide6 не установлен. Установите: pip install PySide6",
              file=sys.stderr)
        return 1
    try:
        from gui.main_window import MainWindow
        app = QApplication(sys.argv)
        app.setApplicationName("Enigma Decoder")
        win = MainWindow()
        win.show()
        return app.exec()
    except Exception:  # noqa: BLE001
        logging.getLogger("enigma_gui").critical("startup failed:\n%s",
                                                 traceback.format_exc())
        try:
            QMessageBox.critical(None, "Operation failed",
                                 "Unable to start the application.\n\n"
                                 f"Details:\n{traceback.format_exc()[-2000:]}")
        except Exception:  # noqa: BLE001
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
