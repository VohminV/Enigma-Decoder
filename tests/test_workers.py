#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests: benchmark в worker-потоке (AUD-005) + shutdown без зависания.

Запуск: pytest test_workers.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_benchmark_core_worker_result_and_cancel():
    from gui.workers.benchmark_worker import BenchmarkWorker
    app = _app()
    got = {}
    w = BenchmarkWorker("core")
    w.result.connect(got.update)
    w.start()
    # GUI-поток не блокирован, пока worker считает
    assert w.isRunning() or got
    deadline = time.perf_counter() + 60
    while w.isRunning() and time.perf_counter() < deadline:
        app.processEvents()
        w.wait(100)
    app.processEvents()
    assert not w.isRunning()
    assert got.get("kind") == "core"
    assert got["positions_tested"] == 26 * 26
    assert got["m3_chars_sec"] > 0

    cancelled = []
    w2 = BenchmarkWorker("core")
    w2.cancelled.connect(lambda: cancelled.append(True))
    w2.cancel()  # отмена до старта
    w2.start()
    deadline = time.perf_counter() + 60
    while w2.isRunning() and time.perf_counter() < deadline:
        app.processEvents()
        w2.wait(100)
    app.processEvents()
    assert cancelled == [True]


def test_close_stops_workers_no_hang():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from gui.main_window import MainWindow
    app = _app()
    win = MainWindow()
    win.show()
    app.processEvents()
    # Crack worker: быстрый исторический поиск
    crack = win.page("Crack")
    crack.date_box.setCurrentText("1941-07-07")
    crack.start()
    # OCR worker: синтетика (долгий inference, отмена — между файлами)
    ocr = win.page("OCR")
    img = Image.new("RGB", (1200, 420), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("cour.ttf", 84)
    except OSError:
        font = ImageFont.load_default(size=84)
    d.text((90, 50), "NCZW VUSX PNYM INHZ", font=font, fill="black")
    ocr._set_array(np.array(img), "test")
    ocr._run_ocr(True)
    t0 = time.perf_counter()
    win.close()
    app.processEvents()
    dt = time.perf_counter() - t0
    # закрытие не висит: отмена + bounded wait (3 c на worker)
    assert dt < 15, f"close took {dt:.1f}s"
    for name in ("Crack", "OCR", "Benchmark"):
        w = getattr(win.page(name), "_worker", None)
        if w is not None:
            w.wait(15000)
            assert not w.isRunning(), name
