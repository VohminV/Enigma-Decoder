#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests Phase 9: known-answer, exhaustive, hillclimb, random, SA, landscape.

Все пороги — измеренные факты TEST SCORER (см. docs/AUDIT.md Phase 9),
NOT REPRESENTATIVE OF REAL HISTORICAL CRYPTANALYSIS.
Deterministic: seed фиксированы.

Запуск: pytest test_search.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import scoring  # noqa: E402
import search_experiments as SX  # noqa: E402
import services  # noqa: E402

TEMPLATE = {"model": "M3", "rotors": ["II", "IV", "V"], "reflector": "B",
            "rings": "BUL", "positions": "AAA",
            "plugs": "AV BS CG DL FU HZ IN KM OW RX",
            "ukw_pos": "A", "ukw_ring": "A"}
TRUE_POS = "MCK"
L = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _scorer():
    return scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)


def _evaluator():
    return SX.PositionEvaluator(dict(TEMPLATE), _scorer())


# --- known-answer ---

def test_known_answer_reproduces_plaintext():
    case = SX.make_case(seed=5, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    assert len(case.plaintext) == 200
    assert case.config["positions"] == TRUE_POS
    ev = _evaluator()
    ev.bind(case.ciphertext)
    plain, _ = ev.evaluate(TRUE_POS)
    assert plain == case.plaintext
    # reference подтверждает шифр
    assert services.build_machine(case.config).decipher(case.plaintext) \
        == case.ciphertext


def test_make_case_deterministic():
    a = SX.make_case(9, 100, dict(TEMPLATE), TRUE_POS)
    b = SX.make_case(9, 100, dict(TEMPLATE), TRUE_POS)
    assert a == b


# --- neighbours ---

def test_neighbours_count_and_cyclic():
    nbs = SX.neighbours("AAA")
    assert len(nbs) == 6 and len(set(nbs)) == 6
    assert "ZAA" in nbs and "BAA" in nbs  # A-1=Z, A+1=B
    nbs = SX.neighbours("AZA")
    assert "AAA" in nbs  # Z+1=A
    # deterministic
    assert SX.neighbours("MCK") == SX.neighbours("MCK")


# --- exhaustive (Experiment A) ---

def test_exhaustive_finds_true_key_len200(capsys):
    case = SX.make_case(seed=21, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    positions = [a + b + c for a in L for b in L for c in L]
    ev = _evaluator()
    rep = SX.exhaustive_search(ev, case.ciphertext, positions, TRUE_POS)
    assert rep.true_rank == 1, rep.true_rank
    top20 = [p for _, p in rep.ranked[:20]]
    assert TRUE_POS in top20
    margin = rep.best_score - sorted((s for s, _ in rep.ranked[1:]),
                                     reverse=True)[0]
    print(f"\nexhaustive len=200: rank 1/17576, margin {margin:.3f}, "
          f"{rep.positions_per_sec:,.0f} pos/sec, {rep.time_s:.1f}s")
    assert rep.positions_per_sec > 0


def test_exhaustive_short_text_len50():
    case = SX.make_case(seed=21, length=50, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    positions = [a + b + c for a in L for b in L for c in L]
    ev = _evaluator()
    rep = SX.exhaustive_search(ev, case.ciphertext, positions, TRUE_POS)
    assert rep.true_rank is not None and rep.true_rank <= 20, rep.true_rank


def test_exhaustive_cancellation():
    case = SX.make_case(seed=21, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    positions = [a + b + c for a in L for b in L for c in L]
    ev = _evaluator()
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] > 500

    try:
        SX.exhaustive_search(ev, case.ciphertext, positions, TRUE_POS,
                             should_cancel=cancel)
        raised = False
    except services.CancelledError:
        raised = True
    assert raised


# --- hill climbing (Experiment B) ---

def test_hillclimb_deterministic_and_bounded():
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    climber = SX.PositionHillClimber(max_iterations=50)
    r1 = climber.climb(ev, "AAA", TRUE_POS, length=200, seed=7)
    ev2 = _evaluator()
    ev2.bind(case.ciphertext)
    r2 = climber.climb(ev2, "AAA", TRUE_POS, length=200, seed=7)
    assert r1.metrics.final_position == r2.metrics.final_position
    assert r1.metrics.iterations <= 50
    assert r1.metrics.evaluations == 1 + r1.metrics.iterations * 6


def test_hillclimb_starts_at_truth_stays():
    # У истины 0 улучшающих соседей: немедленная остановка, success.
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    r = SX.PositionHillClimber().climb(ev, TRUE_POS, TRUE_POS, length=200)
    assert r.metrics.success
    assert r.stopped_reason == "local-optimum"
    assert r.metrics.iterations == 1


def test_hillclimb_cancellation():
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    try:
        SX.PositionHillClimber().climb(ev, "AAA", TRUE_POS,
                                       should_cancel=lambda: True)
        raised = False
    except services.CancelledError:
        raised = True
    assert raised


def test_multistart_documents_golf_course(capsys):
    # Измеренный факт TEST SCORER: жадный поиск застревает в шумовых
    # оптимумах (0/50). Тест фиксирует landscape, не баг.
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    rng = random.Random(7)
    starts = ["".join(rng.choice(L) for _ in range(3)) for _ in range(50)]
    climber = SX.PositionHillClimber()
    best, results = SX.multi_start(climber, ev, starts, TRUE_POS,
                                   length=200, seed=7)
    succ = sum(1 for r in results if r.metrics.success)
    avg_it = sum(r.metrics.iterations for r in results) / len(results)
    print(f"\nmulti-start hillclimb: {succ}/50 success, avg iter {avg_it:.1f}")
    assert succ == 0
    assert avg_it < 10  # застревает почти сразу


# --- random search (Experiment C) ---

def test_random_search_deterministic_and_bounded():
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    r1 = SX.RandomPositionSearch(random.Random(3)).search(ev, 500)
    ev2 = _evaluator()
    ev2.bind(case.ciphertext)
    r2 = SX.RandomPositionSearch(random.Random(3)).search(ev2, 500)
    assert (r1.best_position, r1.best_score) == (r2.best_position, r2.best_score)
    assert r1.evaluations == 500
    assert len(set(r1.sampled)) == 500  # без повторов


def test_random_search_cancellation():
    ev = _evaluator()
    ev.bind("ABCD" * 50)
    try:
        SX.RandomPositionSearch(random.Random(3)).search(
            ev, 5000, should_cancel=lambda: True)
        raised = False
    except services.CancelledError:
        raised = True
    assert raised


# --- simulated annealing (Experiment D) ---

def test_sa_deterministic_and_cooling():
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    ev.bind(case.ciphertext)
    evb = _evaluator()
    evb.bind(case.ciphertext)
    sa1 = SX.SimulatedAnnealer(random.Random(11), **SX.SA_PRESETS["fast"])
    a = sa1.anneal(evb, "AAA", TRUE_POS, length=200)
    evc = _evaluator()
    evc.bind(case.ciphertext)
    sa2 = SX.SimulatedAnnealer(random.Random(11), **SX.SA_PRESETS["fast"])
    b = sa2.anneal(evc, "AAA", TRUE_POS, length=200)
    assert a.metrics.final_position == b.metrics.final_position
    assert a.metrics.final_score == b.metrics.final_score
    temps = a.temperatures
    assert len(temps) == SX.SA_PRESETS["fast"]["steps"]
    assert all(t2 <= t1 for t1, t2 in zip(temps, temps[1:]))
    assert temps[0] > temps[-1]


def test_sa_cancellation():
    ev = _evaluator()
    ev.bind("ABCD" * 50)
    sa = SX.SimulatedAnnealer(random.Random(1), **SX.SA_PRESETS["fast"])
    try:
        sa.anneal(ev, "AAA", should_cancel=lambda: True)
        raised = False
    except services.CancelledError:
        raised = True
    assert raised


def test_sa_presets_reported(capsys):
    case = SX.make_case(seed=7, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    for preset in ("fast", "slow"):
        ev = _evaluator()
        ev.bind(case.ciphertext)
        rng = random.Random(13)
        starts = ["".join(rng.choice(L) for _ in range(3)) for _ in range(10)]
        succ = 0
        for s in starts:
            ev.evaluations = 0
            sa = SX.SimulatedAnnealer(random.Random(13),
                                      **SX.SA_PRESETS[preset])
            if sa.anneal(ev, s, TRUE_POS, length=200).metrics.success:
                succ += 1
        print(f"\nSA {preset}: {succ}/10 success (10 starts, len=200)")


# --- landscape ---

def test_landscape_structure():
    case = SX.make_case(seed=21, length=200, template=dict(TEMPLATE),
                        true_positions=TRUE_POS)
    ev = _evaluator()
    rep = SX.analyze_landscape(ev, case.ciphertext, TRUE_POS,
                               n_random=200, seed=0)
    assert rep["neighbours"] == 6
    assert rep["improving_1"] == 0  # истина — строгий локальный оптимум
    assert rep["second_ring"] == 18  # 6 одноосевых + 12 двухосевых
    assert 0.0 <= rep["p_improving_random"] <= 1.0
    print(f"\nlandscape: true={rep['true_score']:.3f} improving_1=0/6 "
          f"improving_2={rep['improving_2']}/{rep['second_ring']} "
          f"P_improving_random={rep['p_improving_random']:.3f}")


def test_length_table_structure(capsys):
    rows = SX.length_table(dict(TEMPLATE), TRUE_POS)
    assert [r["length"] for r in rows] == [50, 100, 200, 500, 1000, 2000]
    print("\nlength | true | mean_nb | best_nb | improving")
    for r in rows:
        print(f"{r['length']:6d} | {r['true_score']:.3f} | "
              f"{r['mean_neighbour']:.3f} | {r['best_neighbour']:.3f} | "
              f"{r['improving']}/6")
        assert 0 <= r["improving"] <= 6
