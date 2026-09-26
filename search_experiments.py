#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 9: контролируемые эксперименты cryptanalytic search (НЕ production).

Все эксперименты — single-process/single-thread, deterministic при
фиксированном seed, на FastEnigma backend. Reference Enigma — только для
генерации known-answer шифров. Scorer — TEST SCORER (unit-модель),
результаты NOT REPRESENTATIVE OF REAL HISTORICAL CRYPTANALYSIS.

Пространство Phase 9A: rotors/reflector/rings/plugboard фиксированы,
неизвестны только стартовые positions (26^3).
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

import scoring
import services
from fast_enigma import FastEnigma, decode_ints, encode_text

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ---------------------------------------------------------------- корпус


def _test_vocab() -> list[str]:
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "data", "scoring", "test_corpus.txt")
    try:
        with open(path, encoding="utf-8") as f:
            words = f.read().split()
    except OSError as ex:
        raise RuntimeError(f"Не могу прочитать тестовый корпус {path}: {ex}") from ex
    return [w for w in words if w != "X"]


def make_text(rng: random.Random, length: int,
              vocab: list[str] | None = None) -> str:
    """Детерминированный German-like текст заданной длины (слова + X)."""
    vocab = vocab or _test_vocab()
    out: list[str] = []
    total = 0
    while total < length:
        w = rng.choice(vocab)
        out.append(w)
        total += len(w)
    return ("".join(w + "X" for w in out))[:length]


@dataclass(frozen=True)
class ExperimentCase:
    seed: int
    length: int
    plaintext: str
    ciphertext: str
    config: dict  # истинная конфигурация (positions = true key)


def make_case(seed: int, length: int, template: dict,
              true_positions: str) -> ExperimentCase:
    """known plaintext -> known config -> ciphertext (reference core)."""
    rng = random.Random(seed)
    plain = make_text(rng, length)
    cfg = dict(template)
    cfg["positions"] = true_positions
    cipher = services.build_machine(cfg).decipher(plain)
    return ExperimentCase(seed, length, plain, cipher, cfg)


# ---------------------------------------------------------------- evaluator


def neighbours(pos: str) -> list[str]:
    """6 соседей: каждая позиция ±1, циклически (A-1=Z, Z+1=A)."""
    out = []
    for i in range(len(pos)):
        for d in (-1, 1):
            q = list(pos)
            q[i] = LETTERS[(LETTERS.index(q[i]) + d) % 26]
            out.append("".join(q))
    return out


class PositionEvaluator:
    """Подготовленный evaluator: один FastEnigma + set_positions на
    candidate (без reconstruction). Считает evaluations."""

    def __init__(self, config_template: dict, scorer):
        self._fe = FastEnigma.from_config(
            {**config_template, "positions": config_template["positions"]})
        self._scorer = scorer
        self.evaluations = 0
        self._data: list[int] = []

    def evaluate(self, positions: str) -> tuple[str, float]:
        if not self._data:
            raise ValueError("evaluator not bound: call bind(cipher) first")
        self._fe.set_positions(positions)
        plain = decode_ints(self._fe.decrypt_ints(self._data))
        self.evaluations += 1
        return plain, self._scorer.score(plain)

    def bind(self, cipher: str) -> None:
        """Привязать шифр (ints один раз)."""
        self._data = encode_text(cipher)
        self.evaluations = 0


# ---------------------------------------------------------------- метрики


@dataclass
class SearchMetrics:
    length: int = 0
    seed: int = 0
    start_position: str = ""
    final_position: str = ""
    true_position: str = ""
    start_score: float = 0.0
    final_score: float = 0.0
    true_score: float = 0.0
    true_rank: int | None = None
    iterations: int = 0
    evaluations: int = 0
    success: bool = False


# ---------------------------------------------------------------- A: exhaustive


@dataclass
class ExhaustiveReport:
    ranked: list[tuple[float, str]]  # (score, pos) desc
    true_rank: int | None
    true_score: float | None
    best_score: float
    time_s: float
    positions_per_sec: float


def exhaustive_search(evaluator: PositionEvaluator, cipher: str,
                      positions: list[str], true_pos: str | None = None,
                      should_cancel=None,
                      on_progress=None) -> ExhaustiveReport:
    evaluator.bind(cipher)
    scored: list[tuple[float, str]] = []
    t0 = time.perf_counter()
    total = len(positions)
    for i, pos in enumerate(positions):
        if should_cancel is not None and should_cancel():
            raise services.CancelledError(f"exhaustive cancelled at {i}/{total}")
        _, s = evaluator.evaluate(pos)
        scored.append((s, pos))
        if on_progress is not None and (i + 1) % 1024 == 0:
            on_progress(i + 1, total)
    scored.sort(key=lambda e: (-e[0], e[1]))
    dt = time.perf_counter() - t0
    rank = None
    true_score = None
    if true_pos is not None:
        for i, (_, p) in enumerate(scored, 1):
            if p == true_pos:
                rank = i
                true_score = scored[i - 1][0]
                break
    return ExhaustiveReport(scored, rank, true_score, scored[0][0], dt,
                            total / dt if dt > 0 else 0.0)


# ---------------------------------------------------------------- B: hill climbing


@dataclass
class ClimbResult:
    metrics: SearchMetrics
    stopped_reason: str  # "local-optimum" | "max-iterations" (отмена — исключением)


class PositionHillClimber:
    """Жадный подъём по ±1-соседям (эксперимент, не production)."""

    def __init__(self, max_iterations: int = 1000):
        self._max = max_iterations

    def climb(self, evaluator: PositionEvaluator, start: str,
              true_pos: str = "", length: int = 0, seed: int = 0,
              should_cancel=None) -> ClimbResult:
        m = SearchMetrics(length=length, seed=seed, start_position=start,
                          true_position=true_pos)
        _, cs = evaluator.evaluate(start)
        m.start_score = cs
        cur = start
        it = 0
        reason = "max-iterations"
        while it < self._max:
            if should_cancel is not None and should_cancel():
                reason = "cancelled"
                raise services.CancelledError(f"hill climb cancelled at {it}")
            it += 1
            scored = [(evaluator.evaluate(nb)[1], nb)
                      for nb in neighbours(cur)]
            best, bp = max(scored)
            if best > cs:
                cur, cs = bp, best
            else:
                reason = "local-optimum"
                break
        m.final_position = cur
        m.final_score = cs
        m.iterations = it
        m.evaluations = evaluator.evaluations
        m.success = (cur == true_pos) if true_pos else False
        return ClimbResult(m, reason)


def multi_start(climber: PositionHillClimber, evaluator: PositionEvaluator,
                starts: list[str], true_pos: str = "", length: int = 0,
                seed: int = 0, should_cancel=None) -> tuple[ClimbResult, list[ClimbResult]]:
    results = []
    for s in starts:
        if should_cancel is not None and should_cancel():
            raise services.CancelledError("multi-start cancelled")
        evaluator.evaluations = 0
        results.append(climber.climb(evaluator, s, true_pos, length, seed))
    best = max(results, key=lambda r: r.metrics.final_score)
    return best, results


# ---------------------------------------------------------------- C: random


@dataclass
class RandomSearchResult:
    best_position: str
    best_score: float
    evaluations: int
    sampled: list[str] = field(default_factory=list)


class RandomPositionSearch:
    """Baseline случайной выборки (с чем сравнивать hill climbing)."""

    def __init__(self, rng: random.Random):
        self._rng = rng

    def search(self, evaluator: PositionEvaluator, n_samples: int,
               positions: list[str] | None = None,
               should_cancel=None) -> RandomSearchResult:
        pool = positions if positions is not None else \
            [a + b + c for a in LETTERS for b in LETTERS for c in LETTERS]
        sampled = self._rng.sample(pool, min(n_samples, len(pool)))
        best, best_pos = float("-inf"), ""
        for i, pos in enumerate(sampled):
            if should_cancel is not None and should_cancel():
                raise services.CancelledError(f"random search cancelled at {i}")
            _, s = evaluator.evaluate(pos)
            if s > best:
                best, best_pos = s, pos
        return RandomSearchResult(best_pos, best, len(sampled), sampled)


# ---------------------------------------------------------------- D: annealing


@dataclass
class SAResult:
    metrics: SearchMetrics
    temperatures: list[float] = field(default_factory=list)
    accepted: int = 0


SA_PRESETS = {
    "fast": {"t0": 0.3, "alpha": 0.95, "steps": 200},
    "slow": {"t0": 0.5, "alpha": 0.99, "steps": 1000},
}


class SimulatedAnnealer:
    """Минимальный SA (эксперимент). Geometric schedule, deterministic RNG."""

    def __init__(self, rng: random.Random, t0: float, alpha: float,
                 steps: int, tmin: float = 1e-3):
        self._rng = rng
        self._t0 = t0
        self._alpha = alpha
        self._steps = steps
        self._tmin = tmin

    def anneal(self, evaluator: PositionEvaluator, start: str,
               true_pos: str = "", length: int = 0, seed: int = 0,
               should_cancel=None) -> SAResult:
        m = SearchMetrics(length=length, seed=seed, start_position=start,
                          true_position=true_pos)
        _, cs = evaluator.evaluate(start)
        m.start_score = cs
        cur = start
        best, best_pos = cs, start
        temps: list[float] = []
        accepted = 0
        t = self._t0
        for k in range(self._steps):
            if should_cancel is not None and should_cancel():
                raise services.CancelledError(f"SA cancelled at step {k}")
            temps.append(t)
            nb = self._rng.choice(neighbours(cur))
            _, ns = evaluator.evaluate(nb)
            delta = ns - cs
            if delta > 0 or self._rng.random() < math.exp(delta / t):
                cur, cs = nb, ns
                accepted += 1
                if cs > best:
                    best, best_pos = cs, cur
            t = max(t * self._alpha, self._tmin)
        m.final_position = best_pos
        m.final_score = best
        m.iterations = self._steps
        m.evaluations = evaluator.evaluations
        m.success = (best_pos == true_pos) if true_pos else False
        return SAResult(m, temps, accepted)


# ---------------------------------------------------------------- landscape


def analyze_landscape(evaluator: PositionEvaluator, cipher: str,
                      true_pos: str, n_random: int = 200,
                      seed: int = 0) -> dict:
    """Характеристика landscape вокруг истинного ключа."""
    evaluator.bind(cipher)
    rng = random.Random(seed)
    true_plain, true_score = evaluator.evaluate(true_pos)
    first = neighbours(true_pos)
    first_scores = [evaluator.evaluate(nb)[1] for nb in first]
    improving_1 = sum(1 for s in first_scores if s > true_score)
    # второе кольцо: +1 дважды без возврата — уникальных позиций 18
    # (6 по одной оси + 12 двухосевых; упорядоченных путей 30).
    second: set[str] = set()
    for nb in first:
        for nb2 in neighbours(nb):
            if nb2 != true_pos and nb2 not in first:
                second.add(nb2)
    second_scores = [evaluator.evaluate(p)[1] for p in sorted(second)]
    improving_2 = sum(1 for s in second_scores if s > true_score)
    # P(улучшающий сосед) на случайных состояниях
    hits = 0
    for _ in range(n_random):
        p = "".join(rng.choice(LETTERS) for _ in range(3))
        s = evaluator.evaluate(p)[1]
        if any(evaluator.evaluate(nb)[1] > s for nb in neighbours(p)):
            hits += 1
    return {"true_score": true_score,
            "true_plaintext_prefix": true_plain[:40],
            "neighbours": 6,
            "improving_1": improving_1,
            "second_ring": len(second),
            "improving_2": improving_2,
            "p_improving_random": hits / n_random,
            "n_random": n_random}


def length_table(template: dict, true_positions: str,
                 lengths=(50, 100, 200, 500, 1000, 2000),
                 seed_base: int = 1000) -> list[dict]:
    """Таблица §13: true vs 6 соседей для каждой длины."""
    rows = []
    scorer = scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)
    for length in lengths:
        case = make_case(seed_base + length, length, template, true_positions)
        ev = PositionEvaluator(template, scorer)
        ev.bind(case.ciphertext)
        _, ts = ev.evaluate(true_positions)
        ns = [ev.evaluate(nb)[1] for nb in neighbours(true_positions)]
        rows.append({"length": length, "seed": seed_base + length,
                     "true_score": round(ts, 3),
                     "mean_neighbour": round(sum(ns) / 6, 3),
                     "best_neighbour": round(max(ns), 3),
                     "improving": sum(1 for s in ns if s > ts)})
    return rows
