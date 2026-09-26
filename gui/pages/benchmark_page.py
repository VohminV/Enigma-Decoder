#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Benchmark: замер ядра (реален); Fast/Cracker — Not implemented."""
import logging

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("enigma_gui")


class BenchmarkPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        lay = QVBoxLayout(self)
        title = QLabel("Benchmark")
        title.setObjectName("title")
        lay.addWidget(title)

        row = QHBoxLayout()
        self.core_btn = QPushButton("Run Core Benchmark")
        self.core_btn.setToolTip("Замер EnigmaCore в worker-потоке")
        self.fast_btn = QPushButton("Run Fast Benchmark")
        self.fast_btn.setEnabled(False)
        self.fast_btn.setToolTip("FastEnigma не реализован (Phase 5+) — Not implemented")
        self.crack_btn = QPushButton("Run Cracker Benchmark")
        self.crack_btn.setEnabled(False)
        self.crack_btn.setToolTip("CrackerEngine не реализован (Phase 7+) — Not implemented")
        self.ocr_btn = QPushButton("Run OCR Benchmark")
        self.ocr_btn.setToolTip("Замер OCR-пайплайна на синтетике в worker-потоке")
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        for b in (self.core_btn, self.fast_btn, self.crack_btn,
                  self.ocr_btn, self.stop_btn):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.note = QLabel("FastEnigma / Cracker: Not implemented.")
        self.note.setObjectName("muted")
        lay.addWidget(self.note)

        self.result = QLabel("Нажмите Run Core Benchmark.")
        self.result.setObjectName("mono")
        lay.addWidget(self.result)
        self.ocr_result = QLabel("OCR: не замерялся.")
        self.ocr_result.setObjectName("mono")
        lay.addWidget(self.ocr_result)

        lay.addWidget(QLabel("История запусков"))
        self.hist = QTableWidget(0, 5)
        self.hist.setHorizontalHeaderLabels(
            ["Engine", "Chars/sec", "Positions/sec", "Construct ms", "Note"])
        self.hist.verticalHeader().setVisible(False)
        self.hist.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.hist, 1)

        self.core_btn.clicked.connect(lambda: self._launch("core"))
        self.ocr_btn.clicked.connect(lambda: self._launch("ocr"))
        self.stop_btn.clicked.connect(self.on_stop)

    def on_run(self):
        self._launch("core")

    def on_stop(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def _set_running(self, running: bool):
        self.core_btn.setEnabled(not running)
        self.ocr_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def _launch(self, kind: str):
        """Замер в worker-потоке (AUD-005): GUI не блокируется."""
        if self._worker is not None and self._worker.isRunning():
            return
        from gui.workers.benchmark_worker import BenchmarkWorker
        if kind == "core":
            self.result.setText("Замер ядра в worker-потоке…")
        else:
            self.ocr_result.setText("OCR замер в worker-потоке…")
        self._worker = BenchmarkWorker(kind)
        self._worker.stage.connect(self._on_stage)
        self._worker.result.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.error.connect(self._on_error)
        self._set_running(True)
        self._worker.start()

    def _on_stage(self, name):
        self.note.setText(f"Running: {name}… (Stop — отмена)")

    def _on_result(self, r):
        if r.get("kind") == "core":
            self.result.setText(
                f"EnigmaCore: M3 {r['m3_chars_sec']:,} chars/sec, "
                f"M4 {r['m4_chars_sec']:,} chars/sec, "
                f"positions sweep {r['positions_per_sec']:,}/sec "
                f"({r['positions_tested']} tested), construct {r['construct_ms']} ms.")
            row = self.hist.rowCount()
            self.hist.insertRow(row)
            for j, v in enumerate(("EnigmaCore", f"{r['m3_chars_sec']:,}",
                                   f"{r['positions_per_sec']:,}",
                                   str(r["construct_ms"]), "")):
                self.hist.setItem(row, j, QTableWidgetItem(v))
        else:
            self.ocr_result.setText(
                f"OCR {r['engine']} [{r['device']}], image {r['image']}: "
                f"pre {r['preprocess_ms']} ms, ocr {r['ocr_ms']} ms, "
                f"total {r['total_ms']} ms, chars {r['chars']}, "
                f"avg conf {r['avg_confidence'] * 100:.1f}%.")
            row = self.hist.rowCount()
            self.hist.insertRow(row)
            for j, v in enumerate(("OCR", f"{r['chars']} chars", "—", "—",
                                   f"total {r['total_ms']} ms "
                                   f"(pre {r['preprocess_ms']}, ocr {r['ocr_ms']}), "
                                   f"conf {r['avg_confidence']:.2f}")):
                self.hist.setItem(row, j, QTableWidgetItem(v))

    def _done(self):
        self._set_running(False)
        self.note.setText("FastEnigma / Cracker: Not implemented.")
        self._worker = None

    def _on_finished(self, r):
        self._done()

    def _on_cancelled(self):
        self.result.setText("Замер отменён.")
        self.ocr_result.setText("Замер отменён.")
        self._done()

    def _on_error(self, msg):
        log.exception("benchmark worker failed")
        QMessageBox.critical(self, "Benchmark", "Ошибка замера. Подробности в логе.")
        self._done()
