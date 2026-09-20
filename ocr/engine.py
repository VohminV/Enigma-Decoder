#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR-движок: интерфейс + RapidOCR (PP-OCRv6, ONNX CPU, offline).

Модели идут в комплекте пакета rapidocr — загрузка из сети не нужна.
Порядок блоков — построчно сверху вниз (группировка по высоте строки).
"""
from __future__ import annotations

import os

import numpy as np

from ocr.models import OCRBlock


class ModelsMissingError(RuntimeError):
    def __init__(self, detail: str, models_dir: str):
        super().__init__(detail)
        self.models_dir = models_dir


class OCREngine:
    name = "base"

    def is_available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def recognize(self, image_rgb: np.ndarray) -> list[OCRBlock]:
        raise NotImplementedError


def _reading_order(blocks: list[OCRBlock]) -> list[OCRBlock]:
    """Сортировка боксов построчно: сначала строки (по y), внутри — слева."""
    if not blocks:
        return blocks

    def center(b: OCRBlock):
        xs = [p[0] for p in b.box]
        ys = [p[1] for p in b.box]
        return (sum(xs) / 4, sum(ys) / 4)

    heights = []
    for b in blocks:
        ys = [p[1] for p in b.box]
        heights.append(max(ys) - min(ys))
    heights.sort()
    tol = max(heights[len(heights) // 2] * 0.6, 4.0)
    keyed = [(center(b)[0], center(b)[1], b) for b in blocks]
    keyed.sort(key=lambda t: t[1])
    lines: list[list] = []
    for x, y, b in keyed:
        placed = False
        for line in lines:
            if abs(line[0][1] - y) <= tol:
                line.append((x, y, b))
                placed = True
                break
        if not placed:
            lines.append([(x, y, b)])
    out = []
    for line in lines:
        line.sort(key=lambda t: t[0])
        out.extend(t[2] for t in line)
    return out


class RapidOCREngine(OCREngine):
    name = "RapidOCR PP-OCRv6 (ONNX CPU)"

    def __init__(self):
        self._engine = None
        self._models_dir = os.environ.get(
            "RAPIDOCR_MODELS_DIR",
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "data", "ocr_models"))

    @property
    def models_dir(self) -> str:
        return os.path.abspath(self._models_dir)

    def is_available(self) -> tuple[bool, str]:
        try:
            import rapidocr  # noqa: F401
        except ImportError:
            return False, ("Пакет rapidocr не установлен "
                           "(pip install rapidocr). Каталог моделей: "
                           + self.models_dir)
        return True, "ok"

    def _ensure(self):
        ok, msg = self.is_available()
        if not ok:
            raise ModelsMissingError(msg, self.models_dir)
        if self._engine is None:
            import logging
            logging.getLogger("rapidocr").setLevel(logging.WARNING)
            from rapidocr import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image_rgb: np.ndarray) -> list[OCRBlock]:
        engine = self._ensure()
        img = np.ascontiguousarray(image_rgb)
        result = engine(img)
        boxes = result.boxes
        if boxes is None:
            return []

        def _lst(x):
            return list(x) if x is not None else []

        blocks: list[OCRBlock] = []
        for box, text, score in zip(boxes, _lst(result.txts), _lst(result.scores)):
            blocks.append(OCRBlock(text=str(text), score=float(score),
                                   box=[[float(p[0]), float(p[1])] for p in box]))
        return _reading_order(blocks)
