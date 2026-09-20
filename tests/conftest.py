#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pytest-конфигурация: script-style тесты test_core/test_vectors/
test_keydb/test_gui/test_ocr выполняются напрямую
(python tests/<file>), т.к. их код работает на уровне модуля
и завершается sys.exit. Здесь запускаются только pytest-style тесты.
"""
import os

_SCRIPT_TESTS = frozenset({
    "test_core.py",
    "test_vectors.py",
    "test_keydb.py",
    "test_gui.py",
    "test_ocr.py",
})


def pytest_ignore_collect(collection_path, config):
    return os.path.basename(str(collection_path)) in _SCRIPT_TESTS
