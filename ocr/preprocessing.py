#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Предобработка изображений для OCR (cv2/numpy, детерминированная).

Pipeline: resolution check -> crop(ROI) -> deskew -> grayscale ->
contrast(CLAHE) -> denoise -> adaptive threshold -> morphology.
Каждый шаг включается профилем; Original = passthrough.
Входное изображение никогда не мутирует (работаем с копиями).
"""
from __future__ import annotations

import time

import cv2
import numpy as np

from ocr.models import PROFILES, OCRProfile


def to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img.copy()
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)


def estimate_text_height(gray: np.ndarray) -> float:
    """Медианная высота текстовых строк (по проекции), 0 если текста нет."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = bw.shape
    row_frac = (bw > 0).sum(axis=1) / w
    runs, cur = [], 0
    for v in row_frac > 0.02:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    runs = [r for r in runs if r >= 3]
    if not runs:
        return 0.0
    runs.sort()
    return float(runs[len(runs) // 2])


def ensure_min_dim(img: np.ndarray, min_dim: int, max_scale: float = 4.0):
    """Апскейл, если min(w,h) < min_dim. Возвращает (img, scale)."""
    if min_dim <= 0:
        return img.copy(), 1.0
    h, w = img.shape[:2]
    m = min(h, w)
    if m >= min_dim:
        return img.copy(), 1.0
    scale = min(min_dim / m, max_scale)
    new = cv2.resize(img, (int(w * scale), int(h * scale)),
                     interpolation=cv2.INTER_CUBIC)
    return new, scale


def ensure_text_height(img: np.ndarray, target_h: int = 0,
                       max_scale: float = 4.0):
    """Апскейл по медианной высоте текста. Возвращает (img, scale)."""
    if target_h <= 0:
        return img.copy(), 1.0
    gray = to_gray(img)
    med = estimate_text_height(gray)
    if med <= 0 or med >= target_h:
        return img.copy(), 1.0
    scale = min(target_h / med, max_scale)
    h, w = img.shape[:2]
    new = cv2.resize(img, (int(w * scale), int(h * scale)),
                     interpolation=cv2.INTER_LINEAR)
    return new, scale


def estimate_skew(gray: np.ndarray, max_angle: float = 15.0):
    """Оценка наклона через minAreaRect. Возвращает (angle|None, info).

    Не вращаем при низкой уверенности: мало текста или |angle| > max.
    """
    h, w = gray.shape
    small = gray
    if max(h, w) > 800:
        s = 800 / max(h, w)
        small = cv2.resize(gray, (int(w * s), int(h * s)),
                           interpolation=cv2.INTER_AREA)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ys, xs = np.where(bw > 0)
    if len(xs) < 500:
        return None, "too little text"
    coords = np.column_stack((xs, ys)).astype(np.float32)
    angle = cv2.minAreaRect(coords)[-1]
    # minAreaRect: angle в [-90, 0); приводим к наклону текста [-45, 45]
    if angle < -45:
        angle += 90
    if abs(angle) > max_angle:
        return None, f"angle {angle:.1f} exceeds limit"
    if abs(angle) < 0.3:
        return None, "already straight"
    return angle, "ok"


def _projection_score(gray: np.ndarray) -> float:
    """Дисперсия строчного профиля (выше = текст горизонтальнее)."""
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    rows = bw.astype(np.float64).sum(axis=1) / 255.0
    if rows.sum() <= 0:
        return 0.0
    return float(rows.var() / (rows.mean() + 1e-6))


def _bg_color(gray: np.ndarray) -> float:
    """Цвет фона: медиана рамки изображения."""
    h, w = gray.shape
    border = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    return float(np.median(border))


def _rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    h, w = gray.shape
    rot = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, rot, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=_bg_color(gray))


def deskew(gray: np.ndarray, max_angle: float = 15.0,
           min_angle: float = 10.0):
    """Выпрямление. Движок устойчив к крену ~10° сам (замерено), а каждый
    поворот размывает штрихи и вредит детекции — поэтому вращаем только
    при min_angle < |angle| <= max_angle. Иначе — как есть."""
    angle, info = estimate_skew(gray, max_angle)
    if angle is None:
        return gray.copy(), 0.0, info
    if abs(angle) <= min_angle:
        return gray.copy(), 0.0, f"skew {angle:.1f} within engine tolerance"
    # minAreaRect неоднозначен по знаку: проверяем оба варианта проекцией
    base = _projection_score(gray)
    best_angle, best_score = 0.0, base
    for cand in (angle, -angle):
        if abs(cand) < 0.3 or abs(cand) > max_angle:
            continue
        s = _projection_score(_rotate(gray, cand))
        if s > best_score * 1.05:
            best_angle, best_score = cand, s
    if best_angle == 0.0:
        return gray.copy(), 0.0, f"no improvement ({info})"
    return _rotate(gray, best_angle), best_angle, f"signed {info}"


def auto_text_region(gray: np.ndarray, margin: float = 0.03):
    """Грубая оценка текстовой области (контуры). Возвращает rect|None."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9))
    dilated = cv2.dilate(bw, kernel, iterations=2)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    h, w = gray.shape
    best, best_area = None, 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        if area > best_area and area > 0.02 * w * h:
            best, best_area = (x, y, cw, ch), area
    if best is None:
        return None
    x, y, cw, ch = best
    mx, my = int(w * margin), int(h * margin)
    x, y = max(0, x - mx), max(0, y - my)
    cw, ch = min(w - x, cw + 2 * mx), min(h - y, ch + 2 * my)
    return (x, y, cw, ch)


def preprocess(image: np.ndarray, profile: str = "Document",
               roi: tuple | None = None) -> tuple[np.ndarray, dict]:
    """Полный pipeline. Возвращает (обработанное gray, info)."""
    t0 = time.perf_counter()
    if profile not in PROFILES:
        raise ValueError(f"Неизвестный профиль: {profile!r}")
    prof: OCRProfile = PROFILES[profile]
    info: dict = {"profile": profile, "steps": [], "warnings": []}
    img = image.copy()
    h0, w0 = img.shape[:2]
    info["input_size"] = [w0, h0]
    if min(h0, w0) < 300:
        info["warnings"].append("low resolution (<300px)")

    if roi is not None:
        x, y, cw, ch = (max(0, int(v)) for v in roi)
        x2, y2 = min(w0, x + cw), min(h0, y + ch)
        if x2 > x and y2 > y:
            img = img[y:y2, x:x2].copy()
            info["steps"].append(f"crop {x},{y},{x2 - x},{y2 - y}")
            info["roi_offset"] = [x, y]

    img, scale = ensure_text_height(img, prof.upscale_text_height)
    if scale > 1.0:
        info["steps"].append(f"upscale x{scale:.2f}")
    info["scale"] = scale

    gray = to_gray(img)
    info["steps"].append("grayscale")
    if prof.deskew:
        gray, angle, why = deskew(gray, prof.max_deskew_deg)
        info["deskew_angle"] = round(angle, 2)
        info["steps"].append(f"deskew {angle:.2f} ({why})")
    if prof.clahe:
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        info["steps"].append("clahe")
    if prof.denoise:
        gray = cv2.fastNlMeansDenoising(gray, None, h=9,
                                        templateWindowSize=7,
                                        searchWindowSize=21)
        info["steps"].append("denoise")
    if prof.adaptive_thresh:
        gray = cv2.adaptiveThreshold(gray, 255,
                                     cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 51, 12)
        info["steps"].append("adaptive-threshold")
    if prof.morph_open:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel)
        info["steps"].append("morph-open")
    info["output_size"] = [gray.shape[1], gray.shape[0]]
    info["time_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return gray, info
