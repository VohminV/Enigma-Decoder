#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests контрактов Phase 7 (contracts.py): интерфейсы без реализации.

Запуск: pytest test_contracts.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import contracts  # noqa: E402


def test_abstracts_not_instantiable():
    with pytest.raises(TypeError):
        contracts.Scorer()
    with pytest.raises(TypeError):
        contracts.CrackerEngine()


def test_candidate_adapter():
    item = {"entry_id": "e", "message_id": "m", "key": "AAA",
            "plaintext": "HELLO", "config": {"model": "M3"}}
    c = contracts.Candidate.from_historical(item)
    assert c.plaintext == "HELLO"
    assert c.score is None
    assert c.config == {"model": "M3"}
    assert "no scoring" in c.note


def test_no_search_implementation():
    # Контракты не содержат эвристик/моделей: только ABC + dataclasses.
    import inspect
    src = inspect.getsource(contracts)
    assert "ngram" not in src.lower()
    assert "hillclimb" not in src.lower()
