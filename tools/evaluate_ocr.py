#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оценка OCR-пайплайна на синтетической выборке (детерминирована).
Выборка генерируется при запуске (ничего бинарного в репозитории).
Основная метрика для Enigma-шифротекста — CER.

Запуск: python tools/evaluate_ocr.py [--profiles Ciphertext,...]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ocr.pipeline import OCRService  # noqa: E402
from ocr.postprocessing import cer, wer  # noqa: E402

TEXTS = [
    ["NCZW VUSX PNYM INHZ", "XMQX SFWX WLKJ AHSH"],
    ["VONV ONJL OOKS JHFF", "KRKR ALLE XXFOLG"],
    ["DERF UEHR ERIS TTTX", "EINS EINS DREI ZWO"],
]


def render(lines, noise=0.0, angle=0.0, scale=1.0, tint=(255, 255, 255),
           seed=11, size=84):
    img = Image.new("RGB", (1200, 460), tint)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("cour.ttf", size)
    except OSError:
        font = ImageFont.load_default(size=size)
    for i, t in enumerate(lines):
        d.text((90, 50 + i * 160), t, font=font, fill="black")
    if abs(angle) > 0.01:
        img = img.rotate(angle, expand=True, fillcolor="white")
    a = np.array(img).astype(float)
    if noise:
        a += np.random.default_rng(seed).normal(0, noise, a.shape)
    out = Image.fromarray(np.clip(a, 0, 255).astype("uint8"))
    if scale != 1.0:
        out = out.resize((int(1200 * scale), int(out.size[1] * scale)))
    return np.array(out), " ".join("".join(lines).split())


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--profiles", default="Original,Ciphertext,Historical Scan",
                   help="профили через запятую")
    args = p.parse_args()
    profiles = [s.strip() for s in args.profiles.split(",") if s.strip()]

    samples = []
    for li, lines in enumerate(TEXTS):
        samples.append((f"text{li}-clean", render(lines)))
        samples.append((f"text{li}-noisy10", render(lines, noise=10)))
        samples.append((f"text{li}-rot6", render(lines, angle=6)))
        samples.append((f"text{li}-lowres", render(lines, scale=0.6)))
        samples.append((f"text{li}-tint", render(lines, noise=8,
                                                 tint=(233, 223, 201))))

    svc = OCRService()
    print(f"{'sample':16s} {'profile':15s} {'CER':>6s} {'WER':>6s} "
          f"{'conf':>5s} {'ms':>7s}")
    totals: dict = {}
    for name, (img, truth) in samples:
        ref_nospace = "".join(truth.split())
        for prof in profiles:
            r = svc.run(img, profile=prof)
            hyp = r["normalized"].text
            c, w = cer(ref_nospace, hyp), wer(truth, r["raw"])
            conf = r["result"].overall_score
            ms = r["result"].timings_ms["total"]
            print(f"{name:16s} {prof:15s} {c:6.3f} {w:6.3f} "
                  f"{conf:5.2f} {ms:7.1f}")
            t = totals.setdefault(prof, [0.0, 0.0, 0.0, 0])
            t[0] += c
            t[1] += w
            t[2] += conf
            t[3] += 1
    print("-" * 60)
    for prof, (c, w, s, n) in totals.items():
        print(f"{prof:32s} avgCER={c / n:.3f} avgWER={w / n:.3f} "
              f"avgConf={s / n:.2f}")


if __name__ == "__main__":
    main()
