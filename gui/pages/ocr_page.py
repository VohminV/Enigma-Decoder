#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница OCR: image/PDF -> preprocessing -> RapidOCR -> normalize -> Decrypt/Crack.

Исходник не мутирует: original/processed/raw/normalized хранятся отдельно.
Долгие операции — в OCRWorker, GUI не блокируется.
"""
import io
import logging

import numpy as np
from PIL import Image
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget, QMessageBox,
                               QProgressBar, QPushButton, QRubberBand, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

import services
from ocr.models import PROFILES
from ocr.worker import OCRWorker

log = logging.getLogger("enigma_gui")


def np_to_qimage(arr: np.ndarray) -> QImage:
    a = np.ascontiguousarray(arr)
    if a.ndim == 2:
        a = np.stack([a] * 3, axis=-1)
    h, w = a.shape[:2]
    return QImage(a.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def qimage_to_np(img: QImage) -> np.ndarray | None:
    conv = img.convertToFormat(QImage.Format_RGB888)
    w, h = conv.width(), conv.height()
    if w <= 0 or h <= 0:
        return None
    ptr = conv.constBits()
    return np.array(ptr).reshape(h, w, 3).copy()


class PreviewLabel(QLabel):
    """Превью с выбором ROI резинкой. roi_callback(rect|None) в координатах картинки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self._img: np.ndarray | None = None
        self._disp_size = (0, 0)
        self._disp_off = (0, 0)
        self._band = QRubberBand(QRubberBand.Rectangle, self)
        self._origin = None
        self.roi_callback = None

    def set_image(self, arr: np.ndarray | None):
        self._img = arr
        if arr is None:
            self.setPixmap(QPixmap())
            return
        pm = QPixmap.fromImage(np_to_qimage(arr))
        scaled = pm.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._disp_size = (scaled.width(), scaled.height())
        self._disp_off = ((self.width() - scaled.width()) // 2,
                          (self.height() - scaled.height()) // 2)
        canvas = QPixmap(self.size())
        canvas.fill(Qt.transparent)
        p = QPainter(canvas)
        p.drawPixmap(self._disp_off[0], self._disp_off[1], scaled)
        p.end()
        self.setPixmap(canvas)

    def resizeEvent(self, ev):  # noqa: N802
        super().resizeEvent(ev)
        if self._img is not None:
            self.set_image(self._img)

    def _to_image(self, x, y):
        if self._img is None:
            return None
        h, w = self._img.shape[:2]
        dw, dh = self._disp_size
        ox, oy = self._disp_off
        if dw <= 0 or dh <= 0:
            return None
        ix = (x - ox) / dw * w
        iy = (y - oy) / dh * h
        return (min(max(ix, 0), w - 1), min(max(iy, 0), h - 1))

    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.LeftButton and self._img is not None:
            self._origin = ev.position().toPoint()
            self._band.setGeometry(self._origin.x(), self._origin.y(), 0, 0)
            self._band.show()

    def mouseMoveEvent(self, ev):  # noqa: N802
        if self._origin is not None:
            self._band.setGeometry(
                QRect(self._origin, ev.position().toPoint()).normalized())

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if self._origin is None:
            return
        rect = QRect(self._origin, ev.position().toPoint()).normalized()
        self._origin = None
        self._band.hide()
        if rect.width() < 8 or rect.height() < 8 or self._img is None:
            return
        p1 = self._to_image(rect.left(), rect.top())
        p2 = self._to_image(rect.right(), rect.bottom())
        if p1 is None or p2 is None:
            return
        x, y = int(min(p1[0], p2[0])), int(min(p1[1], p2[1]))
        cw, ch = int(abs(p2[0] - p1[0])), int(abs(p2[1] - p1[1]))
        if callable(self.roi_callback):
            self.roi_callback((x, y, cw, ch))


class OCRPage(QWidget):
    request_decrypt_text = None  # callback(text) — задаёт главное окно
    request_crack_text = None  # callback(text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.qs = QSettings("EnigmaDecoder", "enigma")
        self._original: np.ndarray | None = None
        self._processed: np.ndarray | None = None
        self._pre_info: dict = {}
        self._roi: tuple | None = None
        self._show_processed = False
        self._worker: OCRWorker | None = None
        self._pdf_path: str | None = None
        self._pdf_pages: int = 0
        self._last = None

        lay = QVBoxLayout(self)
        title = QLabel("OCR — image / PDF to Enigma text")
        title.setObjectName("title")
        lay.addWidget(title)

        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.preview = PreviewLabel()
        self.preview.roi_callback = self._set_roi
        ll.addWidget(self.preview, 1)
        tog = QHBoxLayout()
        self.btn_orig = QPushButton("Original")
        self.btn_orig.setObjectName("secondary")
        self.btn_proc = QPushButton("Processed")
        self.btn_proc.setObjectName("secondary")
        self.roi_label = QLabel("ROI: full image")
        self.roi_label.setObjectName("muted")
        tog.addWidget(self.btn_orig)
        tog.addWidget(self.btn_proc)
        tog.addWidget(self.roi_label)
        tog.addStretch(1)
        ll.addLayout(tog)
        filerow = QHBoxLayout()
        self.open_img = QPushButton("Open Image")
        self.open_pdf = QPushButton("Open PDF")
        self.open_pdf.setObjectName("secondary")
        self.paste_btn = QPushButton("Paste Image")
        self.paste_btn.setObjectName("secondary")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondary")
        for b in (self.open_img, self.open_pdf, self.paste_btn, self.clear_btn):
            filerow.addWidget(b)
        filerow.addStretch(1)
        ll.addLayout(filerow)
        roirow = QHBoxLayout()
        self.crop_btn = QPushButton("Crop")
        self.crop_btn.setObjectName("secondary")
        self.crop_btn.setToolTip("Выделите область резинкой на превью")
        self.crop_reset = QPushButton("Reset crop")
        self.crop_reset.setObjectName("secondary")
        self.crop_auto = QPushButton("Auto detect text region")
        self.crop_auto.setObjectName("secondary")
        for b in (self.crop_btn, self.crop_reset, self.crop_auto):
            roirow.addWidget(b)
        roirow.addStretch(1)
        ll.addLayout(roirow)
        pdfrow = QHBoxLayout()
        pdfrow.addWidget(QLabel("PDF page"))
        self.pdf_page = QSpinBox()
        self.pdf_page.setRange(1, 1)
        self.pdf_page.setEnabled(False)
        pdfrow.addWidget(self.pdf_page)
        pdfrow.addWidget(QLabel("DPI"))
        self.pdf_dpi = QComboBox()
        self.pdf_dpi.addItems(["150", "200", "300"])
        self.pdf_dpi.setCurrentText("300")
        self.pdf_dpi.setToolTip("300 DPI — точнее (замерено), медленнее")
        pdfrow.addWidget(self.pdf_dpi)
        self.pdf_all = QPushButton("OCR all pages")
        self.pdf_all.setObjectName("secondary")
        self.pdf_all.setEnabled(False)
        pdfrow.addWidget(self.pdf_all)
        pdfrow.addStretch(1)
        ll.addLayout(pdfrow)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.lang_box = QComboBox()
        self.lang_box.addItems(["English", "German"])
        self.lang_box.setToolTip("Обе — латинская модель распознавания")
        self.profile_box = QComboBox()
        self.profile_box.addItems(list(PROFILES))
        self.profile_box.setCurrentText(self.qs.value("ocr_profile", "Ciphertext"))
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Enigma ciphertext", "Historical", "General"])
        self.policy_box = QComboBox()
        self.policy_box.addItems(["Conservative", "Balanced", "Aggressive"])
        self.policy_box.setCurrentText(self.qs.value("ocr_policy", "Conservative"))
        self.policy_box.setToolTip("Conservative: без замен символов, только пометки")
        form.addRow("Language", self.lang_box)
        form.addRow("Profile", self.profile_box)
        form.addRow("OCR Mode", self.mode_box)
        form.addRow("Correction policy", self.policy_box)
        rl.addLayout(form)

        runrow = QHBoxLayout()
        self.pre_btn = QPushButton("PREPROCESS")
        self.pre_btn.setObjectName("secondary")
        self.ocr_btn = QPushButton("OCR")
        self.norm_btn = QPushButton("OCR + NORMALIZE")
        for b in (self.pre_btn, self.ocr_btn, self.norm_btn):
            runrow.addWidget(b)
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        runrow.addWidget(self.stop_btn)
        rl.addLayout(runrow)

        confrow = QHBoxLayout()
        confrow.addWidget(QLabel("Confidence"))
        self.conf_bar = QProgressBar()
        self.conf_bar.setRange(0, 100)
        confrow.addWidget(self.conf_bar, 1)
        self.conf_label = QLabel("—")
        confrow.addWidget(self.conf_label)
        rl.addLayout(confrow)

        rl.addWidget(QLabel("Raw OCR (editable)"))
        self.raw_edit = QTextEdit()
        self.raw_edit.setObjectName("mono")
        self.raw_edit.setMaximumHeight(110)
        rl.addWidget(self.raw_edit)
        rl.addWidget(QLabel("Enigma text (editable)"))
        self.norm_edit = QTextEdit()
        self.norm_edit.setObjectName("mono")
        self.norm_edit.setMaximumHeight(110)
        rl.addWidget(self.norm_edit)
        rl.addWidget(QLabel("Corrections / warnings"))
        self.corr_list = QListWidget()
        self.corr_list.setMaximumHeight(90)
        rl.addWidget(self.corr_list)

        sendrow = QHBoxLayout()
        self.send_dec = QPushButton("Send to Decrypt")
        self.send_crack = QPushButton("Send to Crack")
        self.send_crack.setObjectName("secondary")
        self.norm_only = QPushButton("Normalize ↓")
        self.norm_only.setObjectName("secondary")
        self.norm_only.setToolTip("Перенормализовать исправленный RAW локально")
        for b in (self.send_dec, self.send_crack, self.norm_only):
            sendrow.addWidget(b)
        sendrow.addStretch(1)
        rl.addLayout(sendrow)

        rl.addWidget(QLabel("Batch"))
        batchrow = QHBoxLayout()
        self.batch_add = QPushButton("Add files")
        self.batch_add.setObjectName("secondary")
        self.batch_run = QPushButton("Run OCR")
        self.batch_run.setObjectName("secondary")
        self.batch_clear = QPushButton("Clear")
        self.batch_clear.setObjectName("secondary")
        for b in (self.batch_add, self.batch_run, self.batch_clear):
            batchrow.addWidget(b)
        batchrow.addStretch(1)
        rl.addLayout(batchrow)
        self.batch_table = QTableWidget(0, 4)
        self.batch_table.setHorizontalHeaderLabels(["File", "Text", "Conf", "Time"])
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.batch_table.setMaximumHeight(120)
        rl.addWidget(self.batch_table)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)

        self.status = QLabel("Ready")
        self.status.setObjectName("muted")
        lay.addWidget(self.status)

        # связи
        self.open_img.clicked.connect(self._open_image)
        self.open_pdf.clicked.connect(self._open_pdf)
        self.paste_btn.clicked.connect(self._paste)
        self.clear_btn.clicked.connect(self._clear)
        self.btn_orig.clicked.connect(lambda: self._show(False))
        self.btn_proc.clicked.connect(lambda: self._show(True))
        self.crop_btn.clicked.connect(
            lambda: self.status.setText("Выделите область резинкой на превью"))
        self.crop_reset.clicked.connect(self._roi_reset)
        self.crop_auto.clicked.connect(self._roi_auto)
        self.pre_btn.clicked.connect(self._preprocess)
        self.ocr_btn.clicked.connect(lambda: self._run_ocr(False))
        self.norm_btn.clicked.connect(lambda: self._run_ocr(True))
        self.norm_only.clicked.connect(self._normalize_local)
        self.stop_btn.clicked.connect(self.stop)
        self.send_dec.clicked.connect(self._send_decrypt)
        self.send_crack.clicked.connect(self._send_crack)
        self.batch_add.clicked.connect(self._batch_add)
        self.batch_run.clicked.connect(self._batch_run)
        self.batch_clear.clicked.connect(
            lambda: (self._batch_files.clear(), self.batch_table.setRowCount(0)))
        self.pdf_page.valueChanged.connect(self._pdf_goto)
        self.pdf_all.clicked.connect(lambda: self._run_ocr(True, pdf_all=True))
        self._batch_files: list[str] = []

    # ---------- image sources ----------
    def _set_array(self, arr: np.ndarray | None, note=""):
        self._original = arr
        self._processed = None
        self._pre_info = {}
        self._roi = None
        self._show_processed = False
        self.roi_label.setText("ROI: full image")
        self.preview.set_image(arr)
        self.status.setText(note or "Ready")

    def _open_image(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)")
        if not path:
            return
        try:
            from PIL import Image
            arr = np.array(Image.open(path).convert("RGB"))
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Open image", f"Не могу прочитать: {ex}")
            return
        self._set_array(arr, f"Loaded {path}")

    def _open_pdf(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF (*.pdf)")
        if not path:
            return
        try:
            from ocr.pipeline import render_pdf
            pages = render_pdf(path, dpi=int(self.pdf_dpi.currentText()), pages=[1])
            import fitz
            doc = fitz.open(path)
            n = doc.page_count
            doc.close()
        except ImportError:
            QMessageBox.critical(self, "Open PDF",
                                 "Нужен пакет pymupdf (pip install pymupdf).")
            return
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "Open PDF", f"Не могу прочитать: {ex}")
            return
        self._pdf_path = path
        self._pdf_pages = n
        self.pdf_page.setRange(1, n)
        self._set_array(pages[0][1], f"PDF page 1/{n}")
        self.pdf_page.setEnabled(n > 1)
        self.pdf_all.setEnabled(True)
        self._pdf_path_tmp = path

    def _pdf_goto(self, num):
        if not getattr(self, "_pdf_path_tmp", None):
            return
        try:
            from ocr.pipeline import render_pdf
            pages = render_pdf(self._pdf_path_tmp, dpi=int(self.pdf_dpi.currentText()),
                               pages=[num])
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "PDF", f"Не могу отрендерить: {ex}")
            return
        self._set_array(pages[0][1], f"PDF page {num}/{self._pdf_pages}")
        self._pdf_path = self._pdf_path_tmp

    def _paste(self):
        from PySide6.QtWidgets import QApplication
        md = QApplication.clipboard().mimeData()
        if not md.hasImage():
            QMessageBox.information(self, "Paste", "В буфере нет изображения.")
            return
        arr = qimage_to_np(md.imageData())
        if arr is None:
            return
        self._set_array(arr, "Pasted from clipboard")

    def _clear(self):
        self._set_array(None)
        self._pdf_path = None
        if hasattr(self, "_pdf_path_tmp"):
            del self._pdf_path_tmp
        self.pdf_page.setEnabled(False)
        self.pdf_all.setEnabled(False)
        self.raw_edit.clear()
        self.norm_edit.clear()
        self.corr_list.clear()
        self.conf_bar.setValue(0)
        self.conf_label.setText("—")

    # ---------- ROI / preview ----------
    def _set_roi(self, roi):
        self._roi = roi
        x, y, w, h = roi
        self.roi_label.setText(f"ROI: {x},{y} {w}x{h}")
        self._processed = None
        self._show(False)

    def _roi_reset(self):
        self._roi = None
        self.roi_label.setText("ROI: full image")
        self._processed = None
        self._show(False)

    def _roi_auto(self):
        if self._original is None:
            return
        try:
            from ocr.preprocessing import auto_text_region, to_gray
            rect = auto_text_region(to_gray(self._original))
        except Exception as ex:  # noqa: BLE001
            QMessageBox.warning(self, "Auto region", f"Не получилось: {ex}")
            return
        if rect is None:
            QMessageBox.information(self, "Auto region", "Текстовая область не найдена.")
            return
        self._set_roi(rect)

    def _show(self, processed: bool):
        self._show_processed = processed and self._processed is not None
        self.preview.set_image(self._processed if self._show_processed
                               else self._original)

    def _preprocess(self):
        if self._original is None:
            QMessageBox.information(self, "Preprocess", "Сначала загрузите изображение.")
            return
        try:
            from ocr.preprocessing import preprocess
            out, info = preprocess(self._original, self.profile_box.currentText(),
                                   self._roi)
        except ValueError as ex:
            QMessageBox.warning(self, "Preprocess", str(ex))
            return
        self._processed = out
        self._pre_info = info
        self._show(True)
        steps = "; ".join(info.get("steps", []))
        self.status.setText(f"Preprocessed ({info.get('time_ms')} ms): {steps}")

    # ---------- OCR run ----------
    def _task_base(self):
        from PySide6.QtCore import QSettings
        qs = QSettings("EnigmaDecoder", "enigma")
        return {"profile": self.profile_box.currentText(),
                "mode": ({"General": "General", "Historical": "Historical"}.get(
                    self.mode_box.currentText(), "Enigma ciphertext")),
                "policy": self.policy_box.currentText(),
                "group5": False}

    def _png_bytes(self, arr) -> bytes:
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        return buf.getvalue()

    def _run_ocr(self, fill_normalized: bool, pdf_all: bool = False):
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            from ocr.engine import RapidOCREngine
            ok, msg = RapidOCREngine().is_available()
            if not ok:
                self._models_missing(msg)
                return
        except ImportError:
            self._models_missing("Пакет rapidocr не установлен (pip install rapidocr).")
            return
        task = self._task_base()
        task["fill_normalized"] = fill_normalized
        if pdf_all and getattr(self, "_pdf_path_tmp", None):
            task.update(kind="pdf", source=self._pdf_path_tmp,
                        dpi=int(self.pdf_dpi.currentText()), pages=None)
        elif self._original is None:
            QMessageBox.information(self, "OCR", "Сначала загрузите изображение.")
            return
        else:
            task.update(kind="image", source=self._png_bytes(self._original),
                        roi=self._roi)
        self._launch(task)

    def _models_missing(self, msg):
        box = QMessageBox(self)
        box.setWindowTitle("OCR model is not installed")
        box.setText("OCR model is not installed.\n\n" + msg)
        open_btn = box.addButton("Open model directory", QMessageBox.ActionRole)
        box.addButton("Setup instructions", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked == open_btn:
            import os
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            from ocr.engine import RapidOCREngine
            path = RapidOCREngine().models_dir
            os.makedirs(path, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif clicked is not None and clicked.text() == "Setup instructions":
            QMessageBox.information(
                self, "Setup instructions",
                "1. pip install rapidocr pymupdf\n"
                "2. Модели PP-OCRv6 идут в комплекте пакета rapidocr\n"
                "   (каталог site-packages/rapidocr/models) —\n"
                "   скачивание не требуется, работа полностью offline.\n"
                "3. Перезапустите OCR.")

    def _launch(self, task):
        from ocr.worker import OCRWorker
        self._worker = OCRWorker(task, None)
        self._worker.preprocessing.connect(
            lambda s: self.status.setText("Preprocessing: " + s))
        self._worker.ocr_progress.connect(
            lambda d, t: self.status.setText(f"OCR {d}/{t}…"))
        self._worker.page_progress.connect(
            lambda d, t: self.status.setText(f"Page {d}/{t}…"))
        self._worker.result.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(
            lambda: (self.status.setText("Cancelled"), self._done()))
        self._worker.error.connect(self._on_error)
        self.stop_btn.setEnabled(True)
        self.status.setText("OCR running…")
        self._worker.start()

    def stop(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def on_stop(self):
        self.stop()

    def on_run(self):
        self._run_ocr(True)

    def _done(self):
        self.stop_btn.setEnabled(False)
        self._worker = None

    def _on_result(self, pack):
        blocks = pack["blocks"]
        self.raw_edit.setPlainText(pack["raw"])
        self._highlight(blocks)
        score = pack["score"]
        self.conf_bar.setValue(int(score * 100))
        self.conf_label.setText(f"{score * 100:.1f}%")
        if pack.get("fill_normalized", True):
            self._fill_normalized(pack)

    def _fill_normalized(self, pack):
        self.norm_edit.setPlainText(pack["normalized"])
        self.corr_list.clear()
        for pos, old, new, reason in pack["corrections"]:
            self.corr_list.addItem(f"{pos}: {old}→{new} ({reason})")
        for w in pack["warnings"]:
            self.corr_list.addItem("! " + w)

    def _highlight(self, blocks):
        # подсветка низкоуверенных блоков в raw
        doc_pos = 0
        spans = []
        for b in blocks:
            if b["score"] < 0.6:
                spans.append((doc_pos, doc_pos + len(b["text"])))
            doc_pos += len(b["text"]) + 1
        cur = self.raw_edit.textCursor()
        cur.select(QTextCursor.Document)
        cur.setCharFormat(QTextCharFormat())
        for a, b in spans:
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#8A3030"))
            cur.setCharFormat(fmt)

    def _on_finished(self, data):
        if "combined_normalized" in data:
            self.raw_edit.setPlainText(data.get("combined_raw", ""))
            self.norm_edit.setPlainText(data.get("combined_normalized", ""))
            self.conf_bar.setValue(int(data.get("avg_score", 0) * 100))
            self.conf_label.setText(f"{data.get('avg_score', 0) * 100:.1f}%")
            self.status.setText(f"PDF done: {data.get('pages')} pages")
        else:
            tm = data.get("timings_ms", {})
            self.status.setText(
                f"Done in {tm.get('total', '?')} ms "
                f"(pre {tm.get('preprocess', '?')}, ocr {tm.get('ocr', '?')})")
        self._done()

    def _on_error(self, msg):
        QMessageBox.critical(self, "OCR error", msg)
        self.status.setText("Error")
        self._done()

    # ---------- normalize локально / отправка ----------
    def _normalize_local(self):
        raw = self.raw_edit.toPlainText()
        if not raw.strip():
            return
        try:
            from ocr.postprocessing import EnigmaTextNormalizer
            norm = EnigmaTextNormalizer().normalize(
                raw, None, "Enigma ciphertext", self.policy_box.currentText())
        except ValueError as ex:
            QMessageBox.warning(self, "Normalize", str(ex))
            return
        self.norm_edit.setPlainText(norm.text)
        self.corr_list.clear()
        for c in norm.corrections:
            self.corr_list.addItem(f"{c.pos}: {c.original}→{c.replacement} ({c.reason})")

    def _send_decrypt(self):
        text = self.norm_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Send", "Нет нормализованного текста.")
            return
        if callable(self.request_decrypt_text):
            self.request_decrypt_text(text)

    def _send_crack(self):
        text = "".join(c for c in self.norm_edit.toPlainText().upper()
                       if "A" <= c <= "Z")
        if not text:
            QMessageBox.information(self, "Send", "Нет нормализованного текста.")
            return
        if callable(self.request_crack_text):
            self.request_crack_text(text)

    # ---------- batch ----------
    def _batch_add(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add files", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;PDF (*.pdf)")
        if paths:
            self._batch_files.extend(paths)
            self.status.setText(f"Batch: {len(self._batch_files)} files")

    def _batch_run(self):
        if not self._batch_files:
            QMessageBox.information(self, "Batch", "Добавьте файлы.")
            return
        if self._worker is not None and self._worker.isRunning():
            return
        from ocr.worker import OCRWorker
        task = self._task_base()
        task.update(kind="image", paths=list(self._batch_files))
        self.batch_table.setRowCount(0)
        self._worker = OCRWorker(task, None)
        self._worker.result.connect(self._on_batch_item)
        self._worker.finished.connect(lambda _: self._done())
        self._worker.cancelled.connect(lambda: self._done())
        self._worker.error.connect(self._on_error)
        self.stop_btn.setEnabled(True)
        self._worker.start()

    def _on_batch_item(self, pack):
        from PySide6.QtWidgets import QTableWidgetItem
        r = self.batch_table.rowCount()
        self.batch_table.insertRow(r)
        for j, v in enumerate((pack.get("tag", "")[-40:],
                               pack.get("normalized", "")[:60],
                               str(pack.get("score", "")),
                               str(pack.get("timings_ms", {}).get("total", "")))):
            self.batch_table.setItem(r, j, QTableWidgetItem(v))
