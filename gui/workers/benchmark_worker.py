#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker benchmark'ов: выполняется вне GUI-потока (AUD-005).

Сигналы: started / stage(str) / result(dict) / finished(dict) /
cancelled / error(str). Остановка — кооперативная через should_cancel,
поток никогда не убивается принудительно. parent=None: время жизни
контролирует страница явно (AUD-010).
"""
import time

from PySide6.QtCore import QThread, Signal

import services


class BenchmarkWorker(QThread):
    started = Signal()
    stage = Signal(str)
    result = Signal(dict)
    finished = Signal(dict)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        if kind not in ("core", "ocr"):
            raise ValueError(f"unknown benchmark kind: {kind!r}")
        self._kind = kind
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _cancelled(self):
        return self._cancel or self.isInterruptionRequested()

    def run(self):  # noqa: D102
        try:
            self.started.emit()
            t0 = time.perf_counter()
            if self._kind == "core":
                self.stage.emit("EnigmaCore M3/M4")
                try:
                    res = services.core_benchmark(
                        should_cancel=self._cancelled)
                except services.CancelledError:
                    self.cancelled.emit()
                    return
                if self._cancelled():
                    self.cancelled.emit()
                    return
                pack = {"kind": "core", **res}
            else:
                self.stage.emit("OCR synthetic")
                if self._cancelled():
                    self.cancelled.emit()
                    return
                try:
                    res = services.ocr_benchmark()
                except services.CancelledError:
                    self.cancelled.emit()
                    return
                if self._cancelled():
                    self.cancelled.emit()
                    return
                pack = {"kind": "ocr", **res}
            pack["wall_s"] = round(time.perf_counter() - t0, 2)
            self.result.emit(pack)
            self.finished.emit(pack)
        except Exception as ex:  # noqa: BLE001
            self.error.emit(str(ex))
