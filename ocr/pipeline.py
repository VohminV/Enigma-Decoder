#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCRService: image/PDF -> preprocessing -> engine -> normalize.

Хранит original / processed / raw / normalized отдельно, исходник
не мутирует. Batch API — последовательно (параллелизм — позже).
"""
from __future__ import annotations

import io
import time

import numpy as np
from PIL import Image

from ocr import engine as engine_mod
from ocr.models import OCRResult, NormalizedResult, Timings
from ocr.postprocessing import EnigmaTextNormalizer
from ocr.preprocessing import auto_text_region, preprocess


def load_image_rgba(source) -> np.ndarray:
    """Файл/Binary/PIL -> RGB numpy. Вход не мутирует."""
    from PIL import Image as _Image
    _Image.MAX_IMAGE_PIXELS = 50_000_000
    if isinstance(source, np.ndarray):
        arr = source.copy()
        if arr.size > 50_000_000:
            raise ValueError("Изображение слишком большое (>50 МП). Уменьшите размер.")
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        return arr[:, :, :3].copy()
    if isinstance(source, Image.Image):
        if source.size[0] * source.size[1] > 50_000_000:
            raise ValueError("Изображение слишком большое (>50 МП). Уменьшите размер.")
        return np.array(source.convert("RGB"))
    if isinstance(source, (bytes, bytearray)):
        if len(source) > 30_000_000:
            raise ValueError("Файл изображения слишком большой (>30 МБ).")
        return np.array(Image.open(io.BytesIO(bytes(source))).convert("RGB"))
    # путь к файлу
    import os
    try:
        if os.path.getsize(source) > 30_000_000:
            raise ValueError("Файл изображения слишком большой (>30 МБ).")
    except OSError:
        pass
    return np.array(Image.open(source).convert("RGB"))


def render_pdf(source, dpi: int = 200, pages: list[int] | None = None):
    """PDF -> [(page_no_1based, RGB)]. Требует pymupdf."""
    if not 72 <= int(dpi) <= 400:
        raise ValueError(f"DPI вне диапазона 72..400: {dpi!r}")
    dpi = int(dpi)
    try:
        import fitz
    except ImportError as ex:
        raise RuntimeError("Для PDF нужен пакет pymupdf (pip install pymupdf)") from ex
    if isinstance(source, (bytes, bytearray)):
        doc = fitz.open(stream=bytes(source), filetype="pdf")
    else:
        doc = fitz.open(source)
    out = []
    wanted = set(pages) if pages else set(range(1, doc.page_count + 1))
    for i, page in enumerate(doc, 1):
        if i not in wanted:
            continue
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        out.append((i, np.array(img)))
    doc.close()
    return out


class OCRService:
    def __init__(self, engine=None, normalizer=None):
        self.engine = engine or engine_mod.RapidOCREngine()
        self.normalizer = normalizer or EnigmaTextNormalizer()

    # -- single image --
    def run(self, image, profile: str = "Ciphertext",
            mode: str = "Enigma ciphertext", policy: str = "Conservative",
            roi: tuple | None = None, group5: bool = False,
            auto_roi: bool = False) -> dict:
        t = Timings()
        t0 = time.perf_counter()
        original = load_image_rgba(image)
        t.load_ms = round((time.perf_counter() - t0) * 1000, 1)

        used_roi = roi
        if auto_roi and roi is None:
            from ocr.preprocessing import to_gray
            used_roi = auto_text_region(to_gray(original))

        processed, pre_info = preprocess(original, profile, used_roi)
        t.preprocess_ms = pre_info.get("time_ms", 0.0)

        t1 = time.perf_counter()
        proc_rgb = np.stack([processed] * 3, axis=-1)
        blocks = self.engine.recognize(proc_rgb)
        t.ocr_ms = round((time.perf_counter() - t1) * 1000, 1)

        # координаты боксов — в системе исходника (учитываем ROI и апскейл)
        ox, oy = (pre_info.get("roi_offset") or [0, 0])[:2]
        scale = pre_info.get("scale", 1.0) or 1.0
        for b in blocks:
            b.box = [[p[0] / scale + ox, p[1] / scale + oy] for p in b.box]

        raw = "\n".join(b.text for b in blocks)
        t2 = time.perf_counter()
        norm = self.normalizer.normalize(raw, blocks, mode, policy,
                                         group5=group5)
        t.postprocess_ms = round((time.perf_counter() - t2) * 1000, 1)
        result = OCRResult(blocks=blocks,
                           timings_ms={"load": t.load_ms,
                                       "preprocess": t.preprocess_ms,
                                       "ocr": t.ocr_ms,
                                       "postprocess": t.postprocess_ms,
                                       "total": round(t.total_ms, 1)})
        return {"original": original, "processed": processed,
                "roi": used_roi, "pre_info": pre_info,
                "result": result, "raw": raw, "normalized": norm,
                "timings": t}

    # -- PDF --
    def run_pdf(self, source, dpi: int = 200, pages: list[int] | None = None,
                **kwargs) -> dict:
        rendered = render_pdf(source, dpi, pages)
        page_results = []
        for page_no, img in rendered:
            r = self.run(img, **kwargs)
            r["page"] = page_no
            page_results.append(r)
        combined_raw = "\n".join(f"[p{r['page']}] {r['raw']}" for r in page_results)
        combined_norm = "".join(r["normalized"].text for r in page_results)
        return {"pages": page_results, "combined_raw": combined_raw,
                "combined_normalized": combined_norm}

    # -- batch --
    def batch(self, paths: list[str], on_file=None, **kwargs) -> list[dict]:
        out = []
        for path in paths:
            t0 = time.perf_counter()
            try:
                r = self.run(path, **kwargs)
                status = "ok"
            except Exception as ex:  # noqa: BLE001
                r, status = {}, f"error: {ex}"
            item = {"path": path, "status": status,
                    "time_s": round(time.perf_counter() - t0, 2)}
            if status == "ok":
                item.update({"text": r["normalized"].text,
                             "raw": r["raw"],
                             "confidence": round(r["result"].overall_score, 4),
                             "chars": len(r["normalized"].text)})
            out.append(item)
            if on_file:
                on_file(item)
        return out

    def benchmark(self, image, profile: str = "Ciphertext") -> dict:
        r = self.run(image, profile=profile)
        res: OCRResult = r["result"]
        h, w = r["original"].shape[:2]
        return {"engine": self.engine.name, "device": "CPU (onnxruntime)",
                "image": f"{w}x{h}", "chars": len(r["normalized"].text),
                "avg_confidence": round(res.overall_score, 4),
                **{k + "_ms": v for k, v in res.timings_ms.items()}}
