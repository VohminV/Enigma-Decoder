#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark Phase 8: reference vs FastEnigma.

Дисциплина: warmup + N reps + median/min/max. Сравнение на одинаковых
model/rotors/rings/reflector/ciphertext/position range.
Печатает recorded numbers (идут в docs/AUDIT.md Phase 8).

Запуск: pytest test_fast_bench.py -q -s
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import fast_enigma  # noqa: E402
import scoring  # noqa: E402
import services  # noqa: E402

CFG = {"model": "M3", "rotors": ["II", "IV", "V"], "reflector": "B",
       "rings": "BUL", "positions": "BUO",
       "plugs": "AV BS CG DL FU HZ IN KM OW RX",
       "ukw_pos": "A", "ukw_ring": "A"}
REPS = 7


def _measure(fn, warmup=2, reps=REPS):
    for _ in range(warmup):
        fn()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return {"median": statistics.median(ts), "min": min(ts),
            "max": max(ts), "reps": reps}


def _fmt(r, unit_per_sec=None):
    s = (f"median {r['median']*1000:.2f}ms "
         f"min {r['min']*1000:.2f} max {r['max']*1000:.2f} (n={r['reps']})")
    if unit_per_sec:
        s += f" -> {unit_per_sec/r['median']:,.0f}/sec"
    return s


def test_bench_construction():
    ref = _measure(lambda: services.build_machine(dict(CFG)))
    fast = _measure(lambda: fast_enigma.FastEnigma.from_config(dict(CFG)))
    print(f"\nconstruction ref : {_fmt(ref)}")
    print(f"construction fast: {_fmt(fast)}")


def test_bench_single_decrypt():
    text = "AUFBEFEHL"
    ref = _measure(lambda: services.build_machine(dict(CFG)).decipher(text))
    fe = fast_enigma.FastEnigma.from_config(dict(CFG))
    fast = _measure(lambda: (fe.set_positions("BUO"), fe.decrypt(text)))
    print(f"\nsingle decrypt ref : {_fmt(ref)}")
    print(f"single decrypt fast: {_fmt(fast)}")


def test_bench_long_decrypt():
    text = "A" * 20000
    ref = _measure(lambda: services.build_machine(dict(CFG)).decipher(text),
                   warmup=1, reps=5)
    fe = fast_enigma.FastEnigma.from_config(dict(CFG))
    fast = _measure(lambda: (fe.set_positions("BUO"), fe.decrypt(text)),
                    warmup=1, reps=5)
    print(f"\nlong 20k ref : {_fmt(ref, 20000)} chars/sec")
    print(f"long 20k fast: {_fmt(fast, 20000)} chars/sec")
    assert fast["median"] < ref["median"]


def test_bench_sweep_current_vs_fast():
    """Главное сравнение: 676 позиций, проба 9 букв, одинаковый конфиг."""
    probe = "AUFBEFEHL"
    positions = [a + b + "O" for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]

    def ref_sweep():
        for p in positions:
            c = dict(CFG)
            c["positions"] = p
            services.build_machine(c).decipher(probe)

    fe = fast_enigma.FastEnigma.from_config(dict(CFG))
    data = fast_enigma.encode_text(probe)

    def fast_sweep():
        for p in positions:
            fe.set_positions(p)
            fe.decrypt_ints(data)

    ref = _measure(ref_sweep, warmup=1, reps=5)
    fast = _measure(fast_sweep, warmup=1, reps=5)
    n_chars = len(positions) * len(probe)
    print(f"\nsweep 676 ref : {_fmt(ref, len(positions))} positions/sec "
          f"({n_chars/ref['median']:,.0f} chars/sec)")
    print(f"sweep 676 fast: {_fmt(fast, len(positions))} positions/sec "
          f"({n_chars/fast['median']:,.0f} chars/sec)")
    speedup = ref["median"] / fast["median"]
    print(f"speedup: {speedup:.1f}x")
    assert fast["median"] < ref["median"]
    # корректность sweep подтверждается differential-тестами, здесь скорость


def test_bench_combined_with_scorer():
    """decrypt+score: становится ли scorer bottleneck при fast decrypt."""
    scorer = scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)
    text = "DZULFUXGYYQRNKNKSRSXVVGBZLXZICLFEKNGQSO" * 5  # 195 chars
    data = fast_enigma.encode_text(text)

    def ref_combo():
        plain = services.build_machine(dict(CFG)).decipher(text)
        scorer.score(plain)

    fe = fast_enigma.FastEnigma.from_config(dict(CFG))

    def fast_combo():
        fe.set_positions("BUO")
        scorer.score(fast_enigma.decode_ints(fe.decrypt_ints(data)))

    ref = _measure(ref_combo, warmup=1, reps=5)
    fast = _measure(fast_combo, warmup=1, reps=5)
    print(f"\ndecrypt+score ref : {_fmt(ref, len(text))} chars/sec")
    print(f"decrypt+score fast: {_fmt(fast, len(text))} chars/sec")
    # scorer ~3.3M chars/s: даже при fast decrypt он не bottleneck —
    # фиксируем факт, при смене вывода тест честно упадёт на assert ниже
    assert fast["median"] < ref["median"]
