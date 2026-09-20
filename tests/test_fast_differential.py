#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Differential tests Phase 8: FastEnigma vs reference core (enigma.py).

M3/M4/I: random конфиги (seed фиксирован) × длины 1/5/50/300/1000,
в обе стороны эквивалентно (симметрия — один прогон на свежих машинах).
G/K/D: внешнего эталона нет — random vs own core + roundtrip +
позиционные инварианты (step-таблицы) + существующие vectors.

При failure — полный дамп конфигурации. Normal output чистый.

Запуск: pytest test_fast_differential.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import fast_enigma  # noqa: E402
import services  # noqa: E402

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
SEED = 20260930


def _plugs(rng, npairs):
    bag = list(LETTERS)
    rng.shuffle(bag)
    return " ".join("".join(bag[2 * i:2 * i + 2]) for i in range(npairs))


def _mline_cfg(rng, m4=False):
    pool = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
    if m4:
        wheels = [rng.choice(["Beta", "Gamma"])] + rng.sample(pool, 3)
        refl = rng.choice(["Thin-B", "Thin-C"])
        n = 4
    else:
        wheels = rng.sample(pool, 3)
        refl = rng.choice(["B", "C"])
        n = 3
    return {"model": "M4" if m4 else "M3", "rotors": wheels,
            "reflector": refl,
            "rings": "".join(rng.choice(LETTERS) for _ in range(n)),
            "positions": "".join(rng.choice(LETTERS) for _ in range(n)),
            "plugs": _plugs(rng, rng.randint(0, 10)),
            "ukw_pos": "A", "ukw_ring": "A"}


def _gkd_cfg(rng, model):
    wheels = rng.sample(["I", "II", "III"], 3)
    n = 4 if model.startswith("G") else 3
    cfg = {"model": model, "rotors": wheels,
           "rings": "".join(rng.choice(LETTERS) for _ in range(n)),
           "positions": "".join(rng.choice(LETTERS) for _ in range(n)),
           "plugs": "", "ukw_pos": rng.choice(LETTERS),
           "ukw_ring": rng.choice(LETTERS)}
    return cfg


def _dump(cfg, text, ref_out, fast_out):
    return (f"Machine:\n{cfg['model']}\nRotors:\n{' '.join(cfg['rotors'])}\n"
            f"Reflector:\n{cfg.get('reflector')}\nRings:\n{cfg['rings']}\n"
            f"Positions:\n{cfg['positions']}\n"
            f"Plugboard:\n{cfg.get('plugs') or '-'}\n"
            f"UKW:\n{cfg.get('ukw_pos')}/{cfg.get('ukw_ring')}\n"
            f"ciphertext:\n{text}\nreference:\n{ref_out}\nfast:\n{fast_out}")


def _check(cfg, text):
    ref = services.build_machine(cfg).decipher(text)
    fast = fast_enigma.FastEnigma.from_config(cfg).decrypt(text)
    assert ref == fast, _dump(cfg, text, ref, fast)
    # позиции после прогона тоже обязаны совпасть (stepping-инвариант)
    r2 = services.build_machine(cfg)
    r2.decipher(text)
    f2 = fast_enigma.FastEnigma.from_config(cfg)
    f2.decrypt(text)
    assert r2.positions == f2.positions, \
        _dump(cfg, text, r2.positions, f2.positions)


def _rand_text(rng, n):
    return "".join(rng.choice(LETTERS) for _ in range(n))


def test_m3_random_lengths():
    rng = random.Random(SEED)
    for i in range(30):
        cfg = _mline_cfg(rng)
        for length in (1, 5, 50, 300, 1000):
            try:
                _check(cfg, _rand_text(rng, length))
            except AssertionError as ex:
                raise AssertionError(f"[m3 case {i} len {length}] {ex}") from None


def test_m4_random_lengths():
    rng = random.Random(SEED + 1)
    for i in range(30):
        cfg = _mline_cfg(rng, m4=True)
        for length in (1, 5, 50, 300, 1000):
            try:
                _check(cfg, _rand_text(rng, length))
            except AssertionError as ex:
                raise AssertionError(f"[m4 case {i} len {length}] {ex}") from None


def test_i_random():
    rng = random.Random(SEED + 2)
    for i in range(20):
        cfg = _mline_cfg(rng)
        cfg["model"] = "I"
        cfg["rotors"] = rng.sample(["I", "II", "III", "IV", "V"], 3)
        cfg["reflector"] = rng.choice(["A", "B", "C"])
        for length in (5, 300):
            try:
                _check(cfg, _rand_text(rng, length))
            except AssertionError as ex:
                raise AssertionError(f"[i case {i} len {length}] {ex}") from None


def test_gkd_random_no_external_claim():
    """G/K/D: только vs own core (внешнего эталона нет — см. AUDIT)."""
    rng = random.Random(SEED + 3)
    for i in range(20):
        for model in ("G", "G312", "G260", "K", "D"):
            cfg = _gkd_cfg(rng, model)
            for length in (5, 300):
                try:
                    _check(cfg, _rand_text(rng, length))
                except AssertionError as ex:
                    raise AssertionError(
                        f"[{model} case {i} len {length}] {ex}") from None


def test_g_step_table_positions():
    """Позиционный инвариант carry-шага incl. Lobster (NZAM→ODGW)."""
    cfg = {"model": "G312", "rotors": ["III", "II", "I"],
           "rings": "AAAA", "positions": "NZAM", "plugs": "",
           "ukw_pos": "A", "ukw_ring": "A"}
    want = ["NZAM", "NZAN", "NZAO", "NABP", "NACQ", "OBDR", "OBDS",
            "OCET", "OCEU", "OCFV", "ODGW"]
    f = fast_enigma.FastEnigma.from_config(cfg)
    got = [f.positions]
    data = fast_enigma.encode_text("A" * 10)
    for _ in range(10):
        f.decrypt_ints(data[:1])
        got.append(f.positions)
    assert got == want, got


def test_external_spot_check_mline():
    """Прямая сверка fast vs py-enigma (транзитивность через own core
    уже доказана test_differential + этим файлом, здесь — точечно)."""
    from _ref_loader import load_reference
    ref = load_reference()
    from ref_enigma.machine import EnigmaMachine as RefMachine
    rm = {"B": "B", "C": "C", "Thin-B": "B-Thin", "Thin-C": "C-Thin"}
    rng = random.Random(SEED + 4)
    for i in range(10):
        cfg = _mline_cfg(rng, m4=(i % 2 == 0))
        text = _rand_text(rng, 120)
        r = RefMachine.from_key_sheet(" ".join(cfg["rotors"]),
                                      " ".join(cfg["rings"]),
                                      rm[cfg["reflector"]],
                                      cfg["plugs"] or None)
        r.set_display(cfg["positions"])
        expected = r.process_text(text, replace_char=None)
        got = fast_enigma.FastEnigma.from_config(cfg).decrypt(text)
        assert got == expected, _dump(cfg, text, expected, got)


def test_encode_decode_helpers():
    assert fast_enigma.encode_text("aB c!") == [0, 1, 2]
    assert fast_enigma.decode_ints([0, 1, 25]) == "ABZ"
    f = fast_enigma.FastEnigma.from_config(services.default_config("M3"))
    assert f.decrypt("") == ""
