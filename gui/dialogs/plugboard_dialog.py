#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Диалог Plugboard: клик по двум буквам создаёт пару (макс. 10)."""
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)


class PlugboardDialog(QDialog):
    def __init__(self, initial: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugboard")
        self.setModal(True)
        self._pairs: list[tuple[str, str]] = []
        self._sel: str | None = None
        self._initial_warning = ""
        for token in initial.split():
            t = token.strip().upper()
            if len(t) != 2 or not ("A" <= t[0] <= "Z" and "A" <= t[1] <= "Z"):
                self._initial_warning = f"Пропущена некорректная пара: {token!r}."
                continue
            if t[0] == t[1] or any(t[0] in p or t[1] in p for p in self._pairs):
                self._initial_warning = (
                    f"Пропущена конфликтующая пара: {token!r}."
                )
                continue
            if len(self._pairs) >= 10:
                self._initial_warning = "Начальных пар больше 10: лишние пропущены."
                break
            self._pairs.append((t[0], t[1]))

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Кликните две буквы, чтобы соединить их кабелем."))
        grid = QGridLayout()
        self._btns: dict[str, QPushButton] = {}
        for i in range(26):
            ch = chr(65 + i)
            btn = QPushButton(ch)
            btn.setObjectName("plug")
            btn.setCheckable(False)
            btn.clicked.connect(lambda _=False, c=ch: self._click(c))
            grid.addWidget(btn, i // 13, i % 13)
            self._btns[ch] = btn
        lay.addLayout(grid)
        self.info = QLabel()
        lay.addWidget(self.info)
        if self._initial_warning:
            warn = QLabel(self._initial_warning)
            warn.setObjectName("muted")
            lay.addWidget(warn)
        row = QHBoxLayout()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondary")
        self.clear_btn.clicked.connect(self._clear)
        self.remove_btn = QPushButton("Remove pair")
        self.remove_btn.setObjectName("secondary")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.ok_btn = QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        row.addWidget(self.clear_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        row.addWidget(self.ok_btn)
        lay.addLayout(row)
        self._refresh()

    def _paired(self, ch: str) -> str | None:
        for a, b in self._pairs:
            if ch == a:
                return b
            if ch == b:
                return a
        return None

    def _click(self, ch: str):
        mate = self._paired(ch)
        if mate is not None:
            # клик по занятой букве — выбрать пару для удаления
            self._sel = ch
            self._refresh()
            return
        if self._sel is None or self._paired(self._sel) is not None:
            self._sel = ch
        else:
            if len(self._pairs) >= 10:
                self.info.setText("Максимум 10 пар.")
                self._sel = None
            else:
                self._pairs.append((self._sel, ch))
                self._sel = None
        self._refresh()

    def _clear(self):
        self._pairs = []
        self._sel = None
        self._refresh()

    def _remove_selected(self):
        if self._sel is None:
            return
        mate = self._paired(self._sel)
        if mate is not None:
            self._pairs = [(a, b) for a, b in self._pairs
                           if self._sel not in (a, b)]
        self._sel = None
        self._refresh()

    def _refresh(self):
        used = {c for p in self._pairs for c in p}
        for ch, btn in self._btns.items():
            btn.setProperty("paired", ch in used)
            btn.setProperty("selected", ch == self._sel)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        text = " ".join(a + b for a, b in self._pairs) or "—"
        self.info.setText(f"{text}   ({len(self._pairs)}/10 пар)")

    def pairs(self) -> str:
        return " ".join(a + b for a, b in self._pairs)
