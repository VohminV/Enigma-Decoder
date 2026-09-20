#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR data models: profiles, results, normalization, uncertainty interface."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OCRProfile:
    """Параметры предобработки. upscale_text_height=0 — без апскейла."""
    name: str
    upscale_text_height: int = 0
    deskew: bool = False
    denoise: bool = False
    clahe: bool = False
    adaptive_thresh: bool = False
    morph_open: bool = False
    max_deskew_deg: float = 15.0


PROFILES: dict[str, OCRProfile] = {
    # Original: вход как есть (baseline, воспроизводимость).
    "Original": OCRProfile("Original"),
    "Document": OCRProfile("Document", upscale_text_height=64, clahe=True),
    "Typewritten": OCRProfile("Typewritten", upscale_text_height=64,
                              deskew=True, clahe=True),
    "Historical Scan": OCRProfile("Historical Scan", upscale_text_height=80,
                                  deskew=True, denoise=True, clahe=True,
                                  adaptive_thresh=True, morph_open=True),
    "Photograph": OCRProfile("Photograph", upscale_text_height=80,
                             deskew=True, denoise=True, clahe=True),
    "High Contrast": OCRProfile("High Contrast", upscale_text_height=64,
                                clahe=True, adaptive_thresh=True,
                                morph_open=True),
    # Ciphertext: группы A-Z с машинки; то же, что Typewritten.
    "Ciphertext": OCRProfile("Ciphertext", upscale_text_height=64,
                             deskew=True, clahe=True),
}

CORRECTION_POLICIES = ("Conservative", "Balanced", "Aggressive")
OCR_MODES = ("General", "Historical", "Enigma ciphertext")

# Замены цифра->буква (только в этом направлении: контекст A-Z).
BALANCED_FIXES = {"0": "O", "1": "I", "5": "S", "8": "B"}
AGGRESSIVE_EXTRA = {"6": "G", "2": "Z"}


@dataclass
class OCRBlock:
    text: str
    score: float
    box: list  # [[x,y]x4], координаты исходного изображения


@dataclass
class OCRResult:
    blocks: list[OCRBlock] = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(b.text for b in self.blocks)

    @property
    def overall_score(self) -> float:
        if not self.blocks:
            return 0.0
        return sum(b.score for b in self.blocks) / len(self.blocks)


@dataclass
class OCRCharacter:
    """Интерфейс неопределённости OCR (задел под Crack с альтернативами).

    character: распознанный символ; confidence: уверенность блока 0..1;
    alternatives: кандидаты замены (движок RapidOCR их не даёт —
    поле остаётся пустым, заполнится будущими движками/процедурами).
    """
    character: str
    confidence: float
    alternatives: list[str] = field(default_factory=list)


@dataclass
class Correction:
    pos: int
    original: str
    replacement: str
    reason: str


@dataclass
class NormalizedResult:
    text: str
    corrections: list[Correction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # (pos, char, score) для символов из низкоуверенных блоков
    suspicious: list = field(default_factory=list)


@dataclass
class Timings:
    load_ms: float = 0.0
    preprocess_ms: float = 0.0
    ocr_ms: float = 0.0
    postprocess_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.load_ms + self.preprocess_ms + self.ocr_ms + self.postprocess_ms
