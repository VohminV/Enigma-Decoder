#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests AUD-007: atomic_write_json roundtrip + ownership semantics
_edit_target (импортированный файл read-only, правим локальную копию).

Запуск: pytest test_atomic.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import keydb  # noqa: E402


def test_atomic_write_roundtrip(tmp_path):
    path = str(tmp_path / "sub" / "keys.json")
    data = {"version": 1, "entries": [{"id": "a"}]}
    keydb.atomic_write_json(path, data)
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == data
    # мусора tmp не осталось
    leftovers = [p for p in (tmp_path / "sub").iterdir()
                 if p.name.startswith(".tmp_keys_")]
    assert leftovers == []


def test_atomic_write_overwrite_keeps_valid_json(tmp_path):
    path = str(tmp_path / "keys.json")
    keydb.atomic_write_json(path, {"version": 1, "entries": []})
    keydb.atomic_write_json(path, {"version": 1, "entries": [{"id": "b"}]})
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["entries"] == [{"id": "b"}]


def test_edit_target_ownership(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.pages.keys_page import KeysPage
    _app = QApplication.instance() or QApplication([])
    page = KeysPage()
    default = page._default_db_path()
    # собственная база (или никакая) — правим на месте, не копия
    page._db_path = None
    assert page._edit_target() == (default, False)
    page._db_path = default
    assert page._edit_target() == (default, False)
    # импортированный внешний файл — read-only источник: правим копию
    external = str(tmp_path / "foreign.json")
    with open(external, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": []}, f)
    page._db_path = external
    assert page._edit_target() == (default, True)
