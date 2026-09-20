#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qt-воркер OCR: вне GUI-потока, кооперативная отмена.

Сигналы: started / preprocessing(str) / page_progress(int,int) /
ocr_progress(int,int) / result(dict) / finished(dict) / error(str) /
cancelled. Данные — обычные dict/list/str (без Qt и numpy).
"""
from PySide6.QtCore import QThread, Signal

BATCH_KINDS = ("image", "pdf")


class OCRWorker(QThread):
    started = Signal()
    preprocessing = Signal(str)
    page_progress = Signal(int, int)
    ocr_progress = Signal(int, int)
    result = Signal(dict)
    finished = Signal(dict)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, task: dict, parent=None):
        super().__init__(parent)
        self._task = task
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _cancelled(self):
        return self._cancel or self.isInterruptionRequested()

    def run(self):  # noqa: D102
        try:
            from ocr.pipeline import OCRService
            self.started.emit()
            task = self._task
            kind = task.get("kind", "image")
            service = OCRService()
            if kind == "pdf":
                self.preprocessing.emit("render pdf")
                from ocr.pipeline import render_pdf
                pages = render_pdf(task["source"], task.get("dpi", 200),
                                   task.get("pages"))
                total = len(pages)
                combined, raws, scores = [], [], []
                for i, (page_no, img) in enumerate(pages):
                    if self._cancelled():
                        self.cancelled.emit()
                        return
                    self.page_progress.emit(i + 1, total)
                    self.preprocessing.emit(f"page {page_no}")
                    r = service.run(img, profile=task.get("profile", "Ciphertext"),
                                    mode=task.get("mode", "Enigma ciphertext"),
                                    policy=task.get("policy", "Conservative"),
                                    group5=task.get("group5", False))
                    if self._cancelled():
                        self.cancelled.emit()
                        return
                    self.ocr_progress.emit(i + 1, total)
                    combined.append(r["normalized"].text)
                    raws.append(r["raw"])
                    scores.append(r["result"].overall_score)
                    pack = self._pack(r, page_no)
                    pack["fill_normalized"] = False
                    self.result.emit(pack)
                self.finished.emit({"pages": total,
                                    "combined_normalized": "".join(combined),
                                    "combined_raw": "\n".join(raws),
                                    "avg_score": _avg(scores)})
                return
            # image (+ опциональный batch)
            paths = task.get("paths") or [task.get("source")]
            total = len(paths)
            out = []
            for i, path in enumerate(paths):
                if self._cancelled():
                    self.cancelled.emit()
                    return
                self.page_progress.emit(i + 1, total)
                self.preprocessing.emit(str(path))
                kwargs = {k: task.get(k) for k in
                          ("profile", "mode", "policy", "roi", "group5", "auto_roi")
                          if task.get(k) is not None}
                try:
                    r = service.run(path, **kwargs)
                    packed = self._pack(r, path)
                except Exception as ex:  # noqa: BLE001
                    packed = {"tag": str(path), "blocks": [], "raw": "",
                              "normalized": "", "corrections": [],
                              "warnings": [f"error: {ex}"], "suspicious": [],
                              "score": 0.0, "pre_info": {}, "timings_ms": {}}
                packed["fill_normalized"] = bool(task.get("fill_normalized", True))
                out.append(packed)
                self.result.emit(packed)
            summary = dict(out[0]) if out else {}
            summary["batch"] = out
            summary["total"] = total
            self.finished.emit(summary)
        except Exception as ex:  # noqa: BLE001
            self.error.emit(str(ex))

    @staticmethod
    def _pack(r: dict, tag) -> dict:
        res = r["result"]
        return {"tag": str(tag),
                "blocks": [{"text": b.text, "score": round(b.score, 4),
                            "box": [[round(v, 1) for v in p] for p in b.box]}
                           for b in res.blocks],
                "raw": r["raw"],
                "normalized": r["normalized"].text,
                "corrections": [(c.pos, c.original, c.replacement, c.reason)
                                for c in r["normalized"].corrections],
                "warnings": list(r["normalized"].warnings),
                "suspicious": list(r["normalized"].suspicious),
                "score": round(res.overall_score, 4),
                "pre_info": {k: v for k, v in r["pre_info"].items()
                             if k != "roi_offset"},
                "timings_ms": dict(res.timings_ms)}


def _avg(xs):
    xs = [x for x in xs if x]
    return round(sum(xs) / len(xs), 4) if xs else 0.0
