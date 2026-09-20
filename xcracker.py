#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ExperimentalCracker, Phase 7 — НЕ production cracker.

Маленький контролируемый поиск: фиксированная конфигурация машины,
перебор списка стартовых позиций, оценка Scorer, bounded top-N.
Проверяет полный pipeline: config -> decrypt -> score -> top-N.

Без multiprocessing/GPU/эвристик (запрещено на этом этапе).
"""
from __future__ import annotations

import heapq
import itertools
import time

import scoring
import services
from contracts import Candidate, CrackerEngine, Scorer, SearchProgress


class TopCandidates:
    """Bounded top-N: хранит только лучшие. Детерминированный порядок:
    score по убыванию, tie-break — key (позиции) по возрастанию."""

    def __init__(self, limit: int = 20):
        if limit < 1:
            raise ValueError("limit должен быть >= 1")
        self._limit = limit
        self._heap: list = []

    def push(self, candidate: Candidate) -> bool:
        """Добавить; вернуть True если кандидат вошёл в top-N."""
        entry = (candidate.score if candidate.score is not None
                 else float("-inf"), candidate.key, candidate)
        if len(self._heap) < self._limit:
            heapq.heappush(self._heap, entry)
            return True
        if entry > self._heap[0]:
            heapq.heapreplace(self._heap, entry)
            return True
        return False

    def ordered(self) -> list[Candidate]:
        return [c for _, _, c in
                sorted(self._heap, key=lambda e: (-e[0], e[1]))]

    def __len__(self) -> int:
        return len(self._heap)


def positions_sweep(template: str) -> list[str]:
    """'AB?' -> 26 вариантов; '???' -> 17576. '?' = любая A-Z по порядку.
    Размер ограничивает вызывающий (это experimental инструмент)."""
    pools = ["ABCDEFGHIJKLMNOPQRSTUVWXYZ" if c == "?" else c
             for c in template.upper()]
    return ["".join(p) for p in itertools.product(*pools)]


class ExperimentalCracker(CrackerEngine):
    """Поиск по списку позиций при фиксированной остальной конфигурации.

    config_template: dict services-конфига (model/rotors/reflector/rings/
    plugs; positions подставляется из positions_list).
    positions_list: явный список стартовых позиций (контролируемый объём).
    scorer: реализация contracts.Scorer. top_n: размер top-N.
    """

    def __init__(self, config_template: dict, positions_list: list[str],
                 scorer: Scorer, top_n: int = 20):
        if not positions_list:
            raise ValueError("пустой positions_list")
        self._template = dict(config_template)
        self._positions = list(positions_list)
        self._scorer = scorer
        self._top_n = top_n

    @property
    def total(self) -> int:
        return len(self._positions)

    def search(self, cipher, on_candidate=None, on_progress=None,
               should_cancel=None) -> list[Candidate]:
        text = scoring.normalize_for_scoring(cipher)
        if not text:
            raise ValueError("пустой ciphertext")
        top = TopCandidates(self._top_n)
        total = len(self._positions)
        t0 = time.perf_counter()
        for i, pos in enumerate(self._positions):
            if should_cancel is not None and should_cancel():
                raise services.CancelledError(
                    f"search cancelled at {i}/{total}")
            cfg = dict(self._template)
            cfg["positions"] = pos
            try:
                plain = services.build_machine(cfg).decipher(text)
            except ValueError:
                continue  # битая комбинация шаблона — пропускаем
            cand = Candidate(config=cfg, plaintext=plain,
                             score=self._scorer.score(plain),
                             key=pos,
                             note=f"experimental sweep {cfg.get('model')}")
            if top.push(cand) and on_candidate is not None:
                on_candidate(cand)
            if on_progress is not None and (i + 1) % 64 == 0:
                on_progress(SearchProgress(i + 1, total,
                                           time.perf_counter() - t0))
        if on_progress is not None:
            on_progress(SearchProgress(total, total,
                                       time.perf_counter() - t0))
        return top.ordered()


def benchmark_search(config_template: dict, positions_list: list[str],
                     scorer: Scorer, cipher: str) -> dict:
    """Замер pipeline: decrypt+score/sec и positions/sec (без top-N эвристик
    внутри замера — честный combined throughput)."""
    text = scoring.normalize_for_scoring(cipher)
    n = 0
    t0 = time.perf_counter()
    for pos in positions_list:
        cfg = dict(config_template)
        cfg["positions"] = pos
        plain = services.build_machine(cfg).decipher(text)
        scorer.score(plain)
        n += 1
    dt = time.perf_counter() - t0
    return {"positions": n, "cipher_len": len(text),
            "positions_per_sec": n / dt if dt > 0 else 0.0,
            "decrypt_score_chars_per_sec":
                (n * len(text)) / dt if dt > 0 else 0.0,
            "wall_s": dt}
