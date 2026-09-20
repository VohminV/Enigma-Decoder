#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests AUD-001: services.core_benchmark существует,
импорт services не запускает benchmark, отмена работает.

Запуск: pytest test_services_benchmark.py
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import services  # noqa: E402


def test_core_benchmark_exists():
    assert callable(services.core_benchmark)


def test_import_has_no_side_effects():
    # Перезагрузка модуля не должна запускать замер (иначе импорт вис бы
    # на секунды и выполнял бы работу). Бюджет с запасом: импорт < 2 c.
    import importlib
    t0 = time.perf_counter()
    importlib.reload(services)
    dt = time.perf_counter() - t0
    assert dt < 2.0, f"import services took {dt:.2f}s — benchmark on import?"


def test_core_benchmark_result_shape():
    r = services.core_benchmark(chars=2000)
    assert {"construct_ms", "m3_chars_sec", "m4_chars_sec",
            "positions_per_sec", "positions_tested"} <= set(r)
    assert r["positions_tested"] == 26 * 26
    assert r["m3_chars_sec"] > 0
    assert r["m4_chars_sec"] > 0
    assert r["positions_per_sec"] > 0
    assert r["construct_ms"] >= 0


def test_core_benchmark_cancel():
    with pytest.raises(services.CancelledError):
        services.core_benchmark(chars=2000, should_cancel=lambda: True)
