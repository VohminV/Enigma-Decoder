#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Страница Crack: исторический поиск (реален) + индикатор-солвер (реален).
Полный автоматический поиск: CrackerEngine пока нет (Phase 7+) —
честный статус Not implemented, кнопка отключена."""
import logging

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import services
from gui.workers.crack_worker import CrackWorker

log = logging.getLogger("enigma_gui")


class CrackPage(QWidget):
    request_apply = None  # callback(config) — задаёт главное окно

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: CrackWorker | None = None
        self._results: list[dict] = []
        lay = QVBoxLayout(self)
        title = QLabel("Crack — automatic search")
        title.setObjectName("title")
        lay.addWidget(title)

        # --- индикатор-солвер (реален, мгновенно) ---
        ind = QGroupBox("Indicator solver (message key from daily key + Grundstellung)")
        fl = QFormLayout(ind)
        from gui.widgets.machine_widget import MachineWidget
        self.ind_machine = MachineWidget()
        fl.addRow("Daily key", self.ind_machine)
        self.ind_grund = QTextEdit()
        self.ind_grund.setMaximumHeight(30)
        self.ind_grund.setPlaceholderText("Grundstellung, напр. BUO / NAEM")
        self.ind_ind = QTextEdit()
        self.ind_ind.setMaximumHeight(30)
        self.ind_ind.setPlaceholderText("Indicator, напр. IHO / QEOB")
        self.ind_key = QLabel("—")
        self.ind_key.setObjectName("mono")
        self.ind_solve_btn = QPushButton("Solve key")
        self.ind_solve_btn.setObjectName("secondary")
        fl.addRow("Grundstellung", self.ind_grund)
        fl.addRow("Indicator", self.ind_ind)
        fl.addRow("Message key", self.ind_key)
        fl.addRow("", self.ind_solve_btn)
        lay.addWidget(ind)
        self.ind_solve_btn.clicked.connect(self._solve)

        # --- режим поиска ---
        mode = QGroupBox("Search mode")
        ml = QHBoxLayout(mode)
        self.mode_hist = QRadioButton("Historical lookup")
        self.mode_full = QRadioButton("Full automatic search")
        self.mode_both = QRadioButton("Historical + automatic")
        self.mode_hist.setChecked(True)
        self.mode_full.setEnabled(False)
        self.mode_full.setToolTip("CrackerEngine ещё не реализован (Phase 7+) — Not implemented")
        self.mode_both.setEnabled(False)
        self.mode_both.setToolTip("Automatic search ещё не реализован "
                                  "(Phase 7+) — доступен только Historical lookup")
        ml.addWidget(self.mode_hist)
        ml.addWidget(self.mode_full)
        ml.addWidget(self.mode_both)
        ml.addWidget(QLabel("(Automatic search: Not implemented)"))
        ml.addStretch(1)
        lay.addWidget(mode)

        # --- конфигурация исторического поиска ---
        cfg = QFormLayout()
        self.date_box = QComboBox()
        self.date_box.setToolTip("Дата из базы исторических ключей")
        cfg.addRow("Date", self.date_box)
        self.custom_box = QTextEdit()
        self.custom_box.setMaximumHeight(52)
        self.custom_box.setObjectName("mono")
        self.custom_box.setPlaceholderText(
            "Свой шифротекст (необязательно): каждая конфигурация дня "
            "расшифрует его — для своих перехватов и OCR")
        self.custom_box.setToolTip(
            "Если пусто — расшифровываются сообщения из базы. "
            "Если задан — им расшифровывается каждая конфигурация дня.")
        cfg.addRow("Custom ciphertext", self.custom_box)
        lay.addLayout(cfg)

        row = QHBoxLayout()
        self.start_btn = QPushButton("START CRACK")
        self.start_btn.setToolTip("Исторический поиск по базе (Ctrl+Enter)")
        self.stop_btn = QPushButton("STOP")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        row.addWidget(self.start_btn)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        lay.addLayout(row)

        self.hist_note = QLabel("")
        self.hist_note.setObjectName("muted")
        lay.addWidget(self.hist_note)

        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        stats = QHBoxLayout()
        self.stat_cand = QLabel("Candidates: —")
        self.stat_time = QLabel("Elapsed: —")
        stats.addWidget(self.stat_cand)
        stats.addWidget(self.stat_time)
        stats.addStretch(1)
        lay.addLayout(stats)

        split = QSplitter()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Entry / message", "Key", "Plaintext"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._details)
        split.addWidget(self._wrap("Results", self.table))
        self.detail = QTextEdit()
        self.detail.setObjectName("mono")
        self.detail.setReadOnly(True)
        split.addWidget(self._wrap("Candidate details", self.detail))
        lay.addWidget(split, 1)

        drow = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Configuration")
        self.apply_btn.setToolTip("Отправить конфигурацию на страницу Decrypt")
        self.copy_btn = QPushButton("Copy Plaintext")
        self.copy_btn.setObjectName("secondary")
        self.export_btn = QPushButton("Export Result")
        self.export_btn.setObjectName("secondary")
        for b in (self.apply_btn, self.copy_btn, self.export_btn):
            drow.addWidget(b)
        drow.addStretch(1)
        lay.addLayout(drow)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.apply_btn.clicked.connect(self._apply)
        self.copy_btn.clicked.connect(self._copy)
        self.export_btn.clicked.connect(self._export)
        self.reload_dates()

    def _wrap(self, title, widget):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(title)
        lab.setObjectName("muted")
        lay.addWidget(lab)
        lay.addWidget(widget)
        return w

    def reload_dates(self):
        self.date_box.clear()
        try:
            for e in services.db_entries():
                if self.date_box.findText(e["date"]) < 0:
                    self.date_box.addItem(e["date"])
        except Exception as ex:  # noqa: BLE001
            log.warning("dates load failed: %s", type(ex).__name__)

    # --- indicator solver ---
    def _solve(self):
        try:
            cfg = self.ind_machine.get_config()
            key = services.indicator_solve(
                cfg, self.ind_grund.toPlainText(), self.ind_ind.toPlainText())
            self.ind_key.setText(key)
        except ValueError as ex:
            QMessageBox.warning(self, "Indicator solver", str(ex))
        except Exception:  # noqa: BLE001
            log.exception("indicator solver error")
            QMessageBox.critical(self, "Ошибка", "См. лог.")

    # --- historical search в worker-потоке ---
    def start(self):
        if self._worker is not None and self._worker.isRunning():
            return
        if self.mode_full.isChecked():
            QMessageBox.information(self, "Crack", "Full automatic search: Not implemented.")
            return
        try:
            entries = services.db_entries()
        except Exception as ex:  # noqa: BLE001
            QMessageBox.critical(self, "База ключей", f"Не могу загрузить базу: {ex}")
            return
        date = self.date_box.currentText()
        if not date:
            return
        self._results = []
        self.table.setRowCount(0)
        self.detail.clear()
        self.hist_note.setText(f"Historical search over {date}…")
        custom = "".join(c for c in self.custom_box.toPlainText().upper()
                         if "A" <= c <= "Z") or None
        self._worker = CrackWorker(entries, date, None, custom_cipher=custom)
        self._worker.progress.connect(self._on_progress)
        self._worker.candidate.connect(self._on_candidate)
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.error.connect(self._on_error)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._worker.start()

    def stop(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()

    def set_custom_cipher(self, text: str):
        """Входящее от OCR: свой шифротекст для исторического поиска."""
        self.custom_box.setPlainText(text)

    def on_stop(self):
        self.stop()

    def on_run(self):
        self.start()

    def _on_progress(self, done, total):
        self.bar.setMaximum(max(total, 1))
        self.bar.setValue(done)
        self.stat_cand.setText(f"Candidates: {done} / {total}")

    def _on_candidate(self, item):
        self._results.append(item)
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(str(r + 1)))
        self.table.setItem(r, 1, QTableWidgetItem(
            f"{item['entry_id']} / {item['message_id']}"))
        self.table.setItem(r, 2, QTableWidgetItem(item.get("key", "")))
        self.table.setItem(r, 3, QTableWidgetItem(item["plaintext"][:80]))

    def _on_finished(self, results):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.bar.setValue(self.bar.maximum())
        el = getattr(self._worker, "_elapsed", 0.0)
        self.stat_time.setText(f"Elapsed: {el:.2f} s, found: {len(results)}")
        self.hist_note.setText(
            "Historical lookup done: "
            f"{len(results)} configurations checked. "
            "No scoring available — inspect candidates manually. "
            "Automatic search: Not implemented.")
        self._worker = None

    def _on_cancelled(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.hist_note.setText("Cancelled by user.")
        self._worker = None

    def _on_error(self, msg):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Crack error", msg)
        self._worker = None

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows or not self._results:
            return None
        return self._results[rows[0].row()]

    def _details(self):
        item = self._selected()
        if not item:
            return
        self.detail.setPlainText(
            f"Entry: {item['entry_id']} / {item['message_id']}\n"
            f"Machine: {item['model']}\nRotors: {item['rotors']}\n"
            f"Rings: {item['rings']}\nPositions: {item['positions']}\n"
            f"Reflector: {item['reflector']}\nPlugboard: {item['plugs'] or '—'}\n\n"
            f"Plaintext:\n{item['plaintext']}")

    def _apply(self):
        item = self._selected()
        if not item or not item.get("config"):
            return
        if callable(self.request_apply):
            self.request_apply(item["config"])

    def _copy(self):
        item = self._selected()
        if item:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(item["plaintext"])

    def _export(self):
        item = self._selected()
        if not item:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export result",
                                              f"{item['message_id']}.txt",
                                              "Text (*.txt);;JSON (*.json)")
        if not path:
            return
        try:
            if path.endswith(".json"):
                import json
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({k: v for k, v in item.items() if k != "config"},
                              f, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(item["plaintext"] + "\n")
        except OSError as ex:
            QMessageBox.critical(self, "Export", f"Не могу записать: {ex}")
