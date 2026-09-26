#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offscreen smoke-тест GUI (OCR + Decrypt + Crack worker).
Требует PySide6 и rapidocr. Запуск: python test_gui.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[OK] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {extra}")


try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow
except ImportError as ex:
    print(f"SKIP (нет зависимости): {ex}")
    sys.exit(0)

app = QApplication([])
win = MainWindow()
win.show()
check("sidebar has OCR", any(
    isinstance(win.pages.widget(i), type(win.page("OCR")))
    for i in range(win.pages.count())))

# Decrypt через ядро
dec = win.page("Decrypt")
dec.machine.set_config({"model": "M3", "rotors": ["I", "II", "III"],
                        "reflector": "B", "rings": "AAA", "positions": "AAA",
                        "plugs": "", "ukw_pos": "A", "ukw_ring": "A"})
dec.cipher.setPlainText("BDZGO")
dec.on_run()
check("decrypt BDZGO", dec.plain.toPlainText() == "AAAAA")

# OCR страница end-to-end
ocr = win.page("OCR")
img = Image.new("RGB", (1200, 420), "white")
d = ImageDraw.Draw(img)
try:
    f = ImageFont.truetype("cour.ttf", 84)
except OSError:
    f = ImageFont.load_default(size=84)
for i, t in enumerate(["NCZW VUSX PNYM INHZ", "XMQX SFWX WLKJ AHSH"]):
    d.text((90, 50 + i * 150), t, font=f, fill="black")
ocr._set_array(np.array(img), "test")
ocr.profile_box.setCurrentText("Ciphertext")
ocr._preprocess()
check("preprocess preview", ocr._processed is not None)
ocr._run_ocr(True)
for _ in range(400):
    app.processEvents()
    w = ocr._worker
    if w is None or not w.isRunning():
        break
    w.wait(100)
app.processEvents()
raw = ocr.raw_edit.toPlainText().replace(" ", "").replace("\n", "")
check("ocr raw", raw == "NCZWVUSXPNYMINHZXMQXSFWXWLKJAHSH", repr(raw))
check("normalized editable", ocr.norm_edit.toPlainText() == raw)
check("confidence shown", ocr.conf_bar.value() > 80)

# Send to Decrypt / Crack (через application state, не clipboard)
ocr._send_decrypt()
check("send to decrypt",
      win.pages.currentWidget() is dec
      and dec.cipher.toPlainText() == ocr.norm_edit.toPlainText())
win.goto("OCR")
ocr._send_crack()
crack = win.page("Crack")
check("send to crack",
      win.pages.currentWidget() is crack
      and crack.custom_box.toPlainText() == ocr.norm_edit.toPlainText())

# Crack worker не блокирует (быстрый исторический поиск завершается)
crack.date_box.setCurrentText("1941-07-07")
crack.start()
for _ in range(200):
    app.processEvents()
    w = crack._worker
    if w is None or not w.isRunning():
        break
    w.wait(100)
app.processEvents()
check("crack worker results", len(crack._results) == 1)

print(f"GUI: passed={passed} failed={failed}")
sys.exit(0 if failed == 0 else 1)
