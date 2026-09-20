#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Постобработка: EnigmaTextNormalizer + метрики CER/WER.

Conservative: только чистка (без замен символов), подозрительное помечается.
Balanced: + замены цифра->буква 0/O 1/I 5/S 8/B (каждая логируется).
Aggressive: + 6/G 2/Z.
"""
from __future__ import annotations

from ocr.models import (AGGRESSIVE_EXTRA, BALANCED_FIXES, Correction,
                        NormalizedResult, OCRBlock)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate."""
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate (слова = группы через пробел)."""
    return _wer(reference, hypothesis)


def _wer(reference: str, hypothesis: str) -> float:
    r, h = reference.split(), hypothesis.split()
    if not r:
        return 0.0 if not h else 1.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i]
        for j in range(1, len(h) + 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (r[i - 1] != h[j - 1])))
        prev = cur
    return prev[-1] / len(r)


class EnigmaTextNormalizer:
    def __init__(self, low_conf_threshold: float = 0.6):
        self.low_conf_threshold = low_conf_threshold

    def normalize(self, raw: str, blocks: list[OCRBlock] | None = None,
                  mode: str = "Enigma ciphertext",
                  policy: str = "Conservative",
                  remove_spaces: bool = True,
                  group5: bool = False) -> NormalizedResult:
        if policy not in ("Conservative", "Balanced", "Aggressive"):
            raise ValueError(f"Неизвестная политика: {policy!r}")
        text = raw.upper()
        warnings: list[str] = []
        if mode == "Enigma ciphertext":
            kept, dropped = [], 0
            for ch in text:
                if "A" <= ch <= "Z":
                    kept.append(ch)
                elif ch.isdigit():
                    kept.append(ch)  # цифры чинит политика ниже
                elif ch in (" ", "\n", "\t", "\r"):
                    kept.append(" ")
                else:
                    dropped += 1
            text = "".join(kept)
            if dropped:
                warnings.append(f"удалено посторонних символов: {dropped}")
        else:
            text = " ".join(text.split())

        fixes = {}
        if policy in ("Balanced", "Aggressive"):
            fixes.update(BALANCED_FIXES)
        if policy == "Aggressive":
            fixes.update(AGGRESSIVE_EXTRA)

        out: list[str] = []
        corrections: list[Correction] = []
        for i, ch in enumerate(text):
            if ch in fixes:
                out.append(fixes[ch])
                corrections.append(Correction(i, ch, fixes[ch], policy))
            else:
                out.append(ch)
        text = "".join(out)

        if mode == "Enigma ciphertext" and remove_spaces:
            text = "".join(text.split())
        if group5 and text:
            text = " ".join(text[i:i + 5] for i in range(0, len(text), 5))

        suspicious: list = []
        if blocks:
            pos = 0
            for b in blocks:
                if b.score < self.low_conf_threshold:
                    for j, ch in enumerate(b.text):
                        suspicious.append((pos + j, ch, round(b.score, 3)))
                pos += len(b.text) + 1
            if suspicious:
                warnings.append(
                    f"низкая уверенность (<{self.low_conf_threshold}): "
                    f"{len(suspicious)} символов")
        return NormalizedResult(text=text, corrections=corrections,
                                warnings=warnings, suspicious=suspicious)
