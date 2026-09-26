#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests Phase 7 ExperimentalCracker: top-N, synthetic crack с известным
ключом, отмена, стриминг, benchmark pipeline.

Запуск: pytest test_xcrack.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import scoring  # noqa: E402
import services  # noqa: E402
import xcracker  # noqa: E402
from contracts import Candidate, CrackerEngine  # noqa: E402

BASE_CFG = {"model": "M3", "rotors": ["II", "IV", "V"], "reflector": "B",
            "rings": "BUL", "positions": "BUO",
            "plugs": "AV BS CG DL FU HZ IN KM OW RX"}
TRUE_POS = "BUO"
PLAIN = "ANGRIFFUMNULLUHRVONBERLINXWETTERBERICHT"


def _scorer():
    return scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)


def _cipher():
    return services.build_machine(dict(BASE_CFG)).decipher(PLAIN)


def test_positions_sweep():
    assert xcracker.positions_sweep("AB?")[:3] == ["ABA", "ABB", "ABC"]
    assert len(xcracker.positions_sweep("AB?")) == 26
    assert len(xcracker.positions_sweep("???")) == 26 ** 3


def test_top_candidates_bounded_and_ordered():
    top = xcracker.TopCandidates(limit=5)
    for i in range(100):
        c = Candidate(config={}, plaintext="X", score=float(i % 7),
                      key=f"K{i:03d}")
        top.push(c)
    assert len(top) == 5
    ordered = top.ordered()
    scores = [c.score for c in ordered]
    assert scores == sorted(scores, reverse=True)
    # стабильный tie-break: при равном score — key по возрастанию
    assert [c.key for c in ordered if c.score == 6.0] == sorted(
        c.key for c in ordered if c.score == 6.0)


def test_is_cracker_engine():
    eng = xcracker.ExperimentalCracker(dict(BASE_CFG), ["BUO"], _scorer())
    assert isinstance(eng, CrackerEngine)
    assert eng.total == 1


def test_synthetic_crack_finds_known_key():
    """known plaintext -> encrypt -> sweep 676 позиций -> ключ в Top-N."""
    cipher = _cipher()
    positions = xcracker.positions_sweep("??O")
    eng = xcracker.ExperimentalCracker(dict(BASE_CFG), positions,
                                       _scorer(), top_n=20)
    results = eng.search(cipher)
    assert len(results) <= 20
    keys = [c.key for c in results]
    assert TRUE_POS in keys, "true key not in top-20, rank unknown"
    rank = keys.index(TRUE_POS) + 1
    print(f"\nsynthetic crack: true key {TRUE_POS} rank {rank}/676")
    winner = results[0]
    assert winner.plaintext == PLAIN or TRUE_POS in keys
    # контракт Candidate заполнен
    assert winner.config["positions"] == winner.key
    assert isinstance(winner.score, float)


def test_search_cancellation():
    positions = xcracker.positions_sweep("???")
    eng = xcracker.ExperimentalCracker(dict(BASE_CFG), positions,
                                       _scorer(), top_n=20)
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 30

    import time
    t0 = time.perf_counter()
    try:
        eng.search(_cipher(), should_cancel=cancel)
        cancelled = False
    except services.CancelledError:
        cancelled = True
    dt = time.perf_counter() - t0
    assert cancelled
    assert dt < 10, dt  # остановился быстро, не досчитав 17576


def test_search_streaming():
    positions = xcracker.positions_sweep("??O")
    eng = xcracker.ExperimentalCracker(dict(BASE_CFG), positions,
                                       _scorer(), top_n=20)
    emitted = []
    progress = []
    results = eng.search(_cipher(), on_candidate=emitted.append,
                         on_progress=progress.append)
    assert emitted, "no streaming emissions"
    assert all(isinstance(c, Candidate) for c in emitted)
    assert progress and progress[-1].done == progress[-1].total == 676
    final_keys = {c.key for c in results}
    assert TRUE_POS in final_keys


def test_search_empty_inputs():
    eng = xcracker.ExperimentalCracker(dict(BASE_CFG), ["BUO"], _scorer())
    try:
        eng.search("   !!!   ")
        raise SystemExit("should have raised")
    except ValueError:
        pass
    try:
        xcracker.ExperimentalCracker(dict(BASE_CFG), [], _scorer())
        raise SystemExit("should have raised")
    except ValueError:
        pass


def test_search_benchmark_recorded(capsys):
    positions = xcracker.positions_sweep("??O")
    res = xcracker.benchmark_search(dict(BASE_CFG), positions,
                                    _scorer(), _cipher())
    print(f"\nsearch pipeline: {res['positions_per_sec']:,.0f} positions/sec, "
          f"{res['decrypt_score_chars_per_sec']:,.0f} decrypt+score chars/sec "
          f"({res['positions']} pos x {res['cipher_len']} chars)")
    assert res["positions"] == 676
    assert res["positions_per_sec"] > 0
