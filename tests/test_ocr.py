#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Тесты OCR-модуля: синтетика с известным текстом (детерминирована),
normalizer, предобработка, pipeline. Пороги — по замерам на PP-OCRv6 CPU.
Запуск: python test_ocr.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ocr.engine import RapidOCREngine  # noqa: E402
from ocr.models import PROFILES, OCRCharacter  # noqa: E402
from ocr.pipeline import OCRService, load_image_rgba  # noqa: E402
from ocr.postprocessing import (  # noqa: E402
    EnigmaTextNormalizer,
    cer,
    wer,
)
from ocr.preprocessing import auto_text_region, preprocess, to_gray  # noqa: E402

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"[OK] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name} {extra}")


LINES = ["NCZW VUSX PNYM INHZ", "XMQX SFWX WLKJ AHSH"]
TRUTH = "".join("".join(LINES).split())
FONT = ImageFont.truetype("cour.ttf", 84)


def render(noise=0.0, angle=0.0, scale=1.0, tint=(255, 255, 255), seed=7):
    img = Image.new("RGB", (1200, 420), tint)
    d = ImageDraw.Draw(img)
    for i, t in enumerate(LINES):
        d.text((90, 50 + i * 150), t, font=FONT, fill="black")
    if abs(angle) > 0.01:
        img = img.rotate(angle, expand=True, fillcolor="white")
    a = np.array(img).astype(float)
    if noise:
        rng = np.random.default_rng(seed)
        a += rng.normal(0, noise, a.shape)
    out = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
    if scale != 1.0:
        out = out.resize((int(1200 * scale), int(out.size[1] * scale)))
    return np.array(out)


svc = OCRService()

# --- engine доступен, боксы со скорами ---
ok, _ = RapidOCREngine().is_available()
check("engine available", ok)

# --- точность по профилям ---
cases = [
    ("clean/Ciphertext", render(), "Ciphertext", 0.0),
    ("lowres/Ciphertext", render(scale=0.5), "Ciphertext", 0.0),
    ("rot8/Ciphertext", render(angle=8), "Ciphertext", 0.0),
    ("tint-noise/Historical", render(noise=12, tint=(232, 222, 200)),
     "Historical Scan", 0.0),
    ("noisy15/Historical", render(noise=15), "Historical Scan", 0.0),
]
for name, img, prof, want in cases:
    r = svc.run(img, profile=prof)
    got = r["normalized"].text
    check(f"accuracy {name}", cer(TRUTH, got) == want, f"cer={cer(TRUTH, got):.3f} got={got!r}")
    check(f"scores {name}", all(0.0 <= b.score <= 1.0 for b in r["result"].blocks))

# тяжёлый шум лёгким профилем деградирует (документируем границы профилей)
r = svc.run(render(noise=15), profile="Ciphertext")
check("heavy noise degrades light profile", cer(TRUTH, r["normalized"].text) > 0.05)

# --- normalizer: политики ---
n = EnigmaTextNormalizer()
out = n.normalize("QBFI0 ZO1X I5T", None, "Enigma ciphertext", "Conservative")
check("conservative strips only",
      out.text == "QBFI0ZO1XI5T" and not out.corrections)
out = n.normalize("QBFI0 ZO1X I5T", None, "Enigma ciphertext", "Balanced")
check("balanced fixes+logs",
      out.text == "QBFIOZOIXIST"
      and [(c.pos, c.original, c.replacement) for c in out.corrections]
      == [(4, "0", "O"), (8, "1", "I"), (12, "5", "S")])
out = n.normalize("AB62", None, "Enigma ciphertext", "Aggressive")
check("aggressive 6/2", out.text == "ABGZ")
out = n.normalize("Hello, World! 123", None, "General", "Conservative")
check("general keeps words", out.text == "HELLO, WORLD! 123")
try:
    n.normalize("ABC", None, "Enigma ciphertext", "Wrong")
    check("bad policy raises", False)
except ValueError:
    check("bad policy raises", True)

# --- метрики ---
check("cer basic", abs(cer("ABC", "ADC") - 1 / 3) < 1e-9)
check("cer empty", cer("", "") == 0.0)
check("wer basic", abs(wer("A B C", "A X C") - 1 / 3) < 1e-9)

# --- предобработка детерминирована, исходник цел ---
img = render(noise=5)
before = img.copy()
p1, _ = preprocess(img, "Historical Scan")
p2, _ = preprocess(img, "Historical Scan")
check("preprocess deterministic", np.array_equal(p1, p2))
check("input untouched", np.array_equal(img, before))
check("profiles known", set(PROFILES) >= {"Original", "Document", "Typewritten",
                                          "Historical Scan", "Photograph",
                                          "High Contrast", "Ciphertext"})
rect = auto_text_region(to_gray(img))
check("auto region found", rect is not None and len(rect) == 4)

# --- интерфейс неопределённости ---
ch = OCRCharacter("Q", 0.42, [])
check("uncertainty interface", ch.character == "Q" and ch.confidence == 0.42
      and isinstance(ch.alternatives, list))

# --- batch + PDF ---
with tempfile.TemporaryDirectory() as tmp:
    p1 = os.path.join(tmp, "a.png")
    p2 = os.path.join(tmp, "b.png")
    Image.fromarray(render()).save(p1)
    Image.fromarray(render(angle=-6)).save(p2)
    res = svc.batch([p1, p2], profile="Ciphertext")
    check("batch ok", all(r["status"] == "ok" for r in res) and len(res) == 2)
    check("batch texts", all(r["text"] == TRUTH for r in res),
          str([r["text"] for r in res]))
    # PDF из тех же картинок
    import fitz
    doc = fitz.open()
    for p in (p1, p2):
        page = doc.new_page(width=600, height=300)
        page.insert_image(page.rect, filename=p)
    pdf = os.path.join(tmp, "t.pdf")
    doc.save(pdf)
    doc.close()
    pr = svc.run_pdf(pdf, dpi=300, profile="Ciphertext")
    check("pdf pages", len(pr["pages"]) == 2)
    check("pdf texts", all(TRUTH in (r["normalized"].text) for r in pr["pages"]))

print(f"OCR: passed={passed} failed={failed}")
sys.exit(0 if failed == 0 else 1)
