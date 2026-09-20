#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests Phase 7 Scorer: нормализация, детерминизм, ordering на домене
тестового корпуса, сериализация, throughput.

Запуск: pytest test_scoring.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import scoring  # noqa: E402
from contracts import Scorer  # noqa: E402


def _model():
    return scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)


def test_normalization():
    assert scoring.normalize_for_scoring("HELLO WORLD!") == "HELLOWORLD"
    src = "Abc 123 xYz!"
    assert scoring.normalize_for_scoring(src) == "ABCXYZ"
    assert src == "Abc 123 xYz!"  # вход не мутирует


def test_is_scorer_abc():
    m = _model()
    assert isinstance(m, Scorer)
    assert m.order == 4
    assert m.table_size > 0


def test_deterministic():
    m = _model()
    assert m.score("ANGRIFFUMNULLUHR") == m.score("ANGRIFFUMNULLUHR")


def test_empty_and_short():
    m = _model()
    assert m.score("") == m.floor
    assert m.score("AB") == m.floor  # короче порядка — только floor


def test_natural_beats_random_on_test_domain():
    # Свойство ЭТОГО корпуса (военная лексика), не universal claim.
    m = _model()
    natural = m.score("ANGRIFFUMNULLUHRVONBERLIN")
    gibberish = m.score("XQZJKQWVPMFBLDRTGHYNKSOE")
    assert natural > gibberish, (natural, gibberish)


def test_longer_natural_still_wins():
    m = _model()
    long_nat = m.score("WETTERBERICHTXQDVXNULLUHRVONNORDXFEINDIMOSTEN")
    assert long_nat > m.score("QWZXJKMVPTBLHFDXSNQYURZOIEWPAXCVKLNM")


def test_save_load_roundtrip(tmp_path):
    m = _model()
    path = str(tmp_path / "m.json")
    m.save(path)
    m2 = scoring.NGramScorer.load(path)
    assert m2.order == 4
    assert m2.score("ANGRIFFXBERLIN") == m.score("ANGRIFFXBERLIN")


def test_build_pipeline_reproducible():
    # Пересборка из test_corpus.txt даёт ту же таблицу (reproducible pipeline).
    with open("data/scoring/test_corpus.txt", encoding="utf-8") as f:
        raw = f.read()
    counts = scoring.count_ngrams(raw, 4)
    table, floor = scoring.log_probs_from_counts(counts)
    m = _model()
    assert table == m._table
    assert floor == m.floor


def test_lower_orders_supported():
    with open("data/scoring/test_corpus.txt", encoding="utf-8") as f:
        raw = f.read()
    for order in (1, 2, 3):
        counts = scoring.count_ngrams(raw, order)
        table, floor = scoring.log_probs_from_counts(counts)
        s = scoring.NGramScorer(order, table, floor)
        assert s.score("ANGRIFF") > s.score("XQZJK")


def test_scorer_throughput_recorded(capsys):
    m = _model()
    text = "ANGRIFFUMNULLUHRVONBERLINXWETTERBERICHT" * 10
    import time
    n, t0 = 200, time.perf_counter()
    for _ in range(n):
        m.score(text)
    dt = time.perf_counter() - t0
    chars = n * len(text) / dt
    print(f"\nscorer throughput: {chars:,.0f} chars/sec "
          f"(order=4, {len(text)}-char text)")
    assert chars > 0
