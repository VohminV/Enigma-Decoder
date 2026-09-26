#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Language scoring infrastructure, Phase 7.

Offline, deterministic, без GUI и без зависимости от модели Enigma.
Нормализация скоринга — своя (не OCR pipeline, OCR не трогаем).

Baseline: TetragramScorer (average log10 prob per tetragram).
"""
from __future__ import annotations

import json
import math
import os

from contracts import Scorer

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Тестовая модель для unit tests (маленькая, детерминированная).
# НЕ выдавать за production языковую модель (см. data/scoring/README.md).
TEST_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "data", "scoring", "test_tetragrams.json")


def normalize_for_scoring(text: str) -> str:
    """Скоринговая нормализация: только A-Z uppercase без пробелов.

    "HELLO WORLD!" -> "HELLOWORLD". Вход не мутирует (возвращает новую
    строку); отделена от OCR-нормализации намеренно.
    """
    return "".join(c for c in text.upper() if "A" <= c <= "Z")


class NGramScorer(Scorer):
    """n-граммный scorer (order 1..4). score = средний log10 prob на n-грамму.

    Выше = правдоподобнее. Невиданные n-граммы получают floor.
    Детерминирован: суммирование идёт по порядку текста.
    """

    name = "ngram"

    def __init__(self, order: int, log_probs: dict[str, float],
                 floor: float, name: str | None = None):
        if not 1 <= order <= 4:
            raise ValueError(f"order должен быть 1..4, получен {order}")
        if not log_probs:
            raise ValueError("пустая n-gram таблица")
        self._order = order
        self._table = dict(log_probs)
        self._floor = float(floor)
        if name is not None:
            self.name = name

    @property
    def order(self) -> int:
        return self._order

    @property
    def floor(self) -> float:
        return self._floor

    @property
    def table_size(self) -> int:
        return len(self._table)

    def score(self, text: str) -> float:
        norm = normalize_for_scoring(text)
        grams = [norm[i:i + self._order]
                 for i in range(len(norm) - self._order + 1)]
        if not grams:
            # текст короче порядка: нечего оценивать, только floor
            return self._floor
        total = 0.0
        for g in grams:
            total += self._table.get(g, self._floor)
        return total / len(grams)

    def to_dict(self) -> dict:
        return {"name": self.name, "order": self._order,
                "floor": self._floor, "log_probs": self._table}

    @classmethod
    def from_dict(cls, data: dict) -> "NGramScorer":
        order = int(data["order"])
        if order == 4:
            return TetragramScorer(dict(data["log_probs"]),
                                   float(data["floor"]),
                                   str(data.get("name", "tetragram")))
        return cls(order, dict(data["log_probs"]), float(data["floor"]),
                   str(data.get("name", f"{order}-gram")))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, sort_keys=True)

    @classmethod
    def load(cls, path: str) -> "NGramScorer":
        size = os.path.getsize(path)
        if size > 50_000_000:
            raise ValueError(
                f"Модель скорера слишком большая: {size} байт (лимит 50 МБ)."
            )
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "order" not in data:
            raise ValueError("bad scorer model format")
        return cls.from_dict(data)


class TetragramScorer(NGramScorer):
    """Baseline Phase 7: тетраграммы."""

    name = "tetragram"

    def __init__(self, log_probs: dict[str, float], floor: float,
                 name: str = "tetragram"):
        super().__init__(4, log_probs, floor, name)


def count_ngrams(text: str, order: int) -> dict[str, int]:
    """Подсчёт n-грамм нормализованного текста (для builder'а)."""
    norm = normalize_for_scoring(text)
    counts: dict[str, int] = {}
    for i in range(len(norm) - order + 1):
        g = norm[i:i + order]
        counts[g] = counts.get(g, 0) + 1
    return counts


def log_probs_from_counts(counts: dict[str, int],
                          floor_count: float = 0.01) -> tuple[dict[str, float], float]:
    """counts -> (log10 probs, floor). Детерминировано."""
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("пустой корпус")
    table = {g: math.log10(c / total) for g, c in counts.items()}
    return table, math.log10(floor_count / total)
