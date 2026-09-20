#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker исторического поиска: выполняется вне GUI-потока.

Сигналы: started / progress(done, total) / candidate(dict) /
finished(list) / cancelled / error(str). Остановка — кооперативная,
поток никогда не убивается принудительно. QWidget внутрь не передаётся.
"""
import time

from PySide6.QtCore import QThread, Signal

import services


class CrackWorker(QThread):
    started = Signal()
    progress = Signal(int, int)
    candidate = Signal(dict)
    finished = Signal(list)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, entries: list[dict], date: str, parent=None,
                 custom_cipher: str | None = None):
        super().__init__(parent)
        self._entries = entries
        self._date = date
        self._custom_cipher = (custom_cipher or "").strip() or None
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):  # noqa: D102
        try:
            self.started.emit()
            # кандидаты: каждое сообщение дня с известным ключом
            jobs = []
            for e in self._entries:
                if e["date"] != self._date or e["status"] != "verified":
                    continue
                for m in e.get("messages", []):
                    if m.get("cipher") and m.get("key"):
                        jobs.append((e, m))
            total = len(jobs)
            results = []
            t0 = time.perf_counter()
            for i, (e, m) in enumerate(jobs):
                if self._cancel or self.isInterruptionRequested():
                    self.cancelled.emit()
                    return
                try:
                    cfg = services.entry_machine_config(e, m["key"])
                    cipher = self._custom_cipher or m["cipher"]
                    plain = services.build_machine(cfg).decipher(cipher)
                    item = {"entry_id": e["id"], "message_id": m["id"],
                            "model": e["model"],
                            "rotors": " ".join(cfg["rotors"]),
                            "rings": cfg["rings"], "positions": m["key"],
                            "key": m.get("key", ""),
                            "reflector": cfg.get("reflector", "—"),
                            "plugs": cfg.get("plugs", ""),
                            "plaintext": plain, "config": cfg}
                except Exception as ex:  # noqa: BLE001
                    item = {"entry_id": e["id"], "message_id": m["id"],
                            "model": e["model"], "rotors": "", "rings": "",
                            "positions": "", "key": m.get("key", ""),
                            "reflector": "", "plugs": "",
                            "plaintext": f"<ошибка: {ex}>", "config": None}
                results.append(item)
                self.candidate.emit(item)
                self.progress.emit(i + 1, total)
            self._elapsed = time.perf_counter() - t0
            self.finished.emit(results)
        except Exception as ex:  # noqa: BLE001
            self.error.emit(str(ex))
