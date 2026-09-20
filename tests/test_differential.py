#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Differential tests AUD-008: собственный Core vs независимый reference.

Reference: py-enigma 1.0.2 (Brian Neal, MIT, данные Rijmenants) —
покрывает M-line (I–VIII, Beta/Gamma, B/C/B-Thin/C-Thin, double-step).
G/K/D reference не найден (нет публичных реализаций) — для них остаются
внутренние step-таблицы из файлов симулятора Enigma 1.x (legacy.py);
см. AUDIT.md Remediation/AUD-008 (OPEN).

Примечание: топ-модуль проекта `enigma.py` затеняет pip-пакет `enigma`,
поэтому reference грузится через importlib под именем ref_enigma
(ничего из sys.path/sys.modules production-кода не трогаем).

Запуск: pytest test_differential.py
"""
import importlib.util
import os
import random
import sys
import sysconfig

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import services  # noqa: E402

REF_VERSION = "1.0.2"


def _load_reference():
    for key in ("purelib", "platlib"):
        init = os.path.join(sysconfig.get_path(key), "enigma", "__init__.py")
        if os.path.exists(init):
            pkg_dir = os.path.dirname(init)
            spec = importlib.util.spec_from_file_location(
                "ref_enigma", init, submodule_search_locations=[pkg_dir])
            mod = importlib.util.module_from_spec(spec)
            sys.modules["ref_enigma"] = mod
            spec.loader.exec_module(mod)
            return mod
    pytest.skip("reference py-enigma not installed (pip install -e '.[dev]')")


ref = _load_reference()

_REFLECTOR_MAP = {"B": "B", "C": "C", "Thin-B": "B-Thin", "Thin-C": "C-Thin"}


def _ref_machine(cfg):
    """Наш cfg -> reference-машина с теми же настройками."""
    from ref_enigma.machine import EnigmaMachine as RefMachine
    rotors = " ".join(cfg["rotors"])
    rings = " ".join(cfg["rings"])
    refl = _REFLECTOR_MAP[cfg["reflector"]]
    plugs = cfg.get("plugs", "") or None
    m = RefMachine.from_key_sheet(rotors, rings, refl, plugs)
    m.set_display(cfg["positions"])
    return m


def _compare(cfg, text):
    """Own vs reference в обе стороны. При расхождении — полный дамп."""
    cipher_own = services.build_machine(cfg).decipher(text)
    cipher_ref = _ref_machine(cfg).process_text(text, replace_char=None)
    context = (f"Machine:\n{cfg['model']}\nRotors:\n{' '.join(cfg['rotors'])}\n"
               f"Rings:\n{cfg['rings']}\nPositions:\n{cfg['positions']}\n"
               f"Reflector:\n{cfg.get('reflector')}\n"
               f"Plugboard:\n{cfg.get('plugs') or '-'}\nInput:\n{text}")
    assert cipher_own == cipher_ref, \
        f"{context}\nExpected (reference):\n{cipher_ref}\nActual (own):\n{cipher_own}"
    # обратное направление свежими машинами
    plain_own = services.build_machine(cfg).decipher(cipher_ref)
    plain_ref = _ref_machine(cfg).process_text(cipher_ref, replace_char=None)
    assert plain_own == text, f"{context}\nOwn decipher mismatch:\n{plain_own}"
    assert plain_ref == text, f"{context}\nRef decipher mismatch:\n{plain_ref}"


def test_reference_sanity():
    # Reference сам проходит классику M3 AAAAA -> BDZGO
    m = _ref_machine({"model": "M3", "rotors": ["I", "II", "III"],
                      "reflector": "B", "rings": "AAA", "positions": "AAA",
                      "plugs": ""})
    assert m.process_text("AAAAA", replace_char=None) == "BDZGO"


def test_historic_vectors_differential():
    # Исторические векторы проекта через ОБА движка
    _compare({"model": "M3", "rotors": ["I", "II", "III"], "reflector": "B",
              "rings": "AAA", "positions": "AAA", "plugs": ""}, "AAAAA")
    _compare({"model": "M4",
              "rotors": ["Beta", "II", "IV", "I"], "reflector": "Thin-B",
              "rings": "AAAV", "positions": "VJNA",
              "plugs": "AT BL DF GJ HM NW OP QY RZ VX"},
             "VONVONJLOOKSJHFFTTTEINSEINSDREIZWO")
    _compare({"model": "M4",
              "rotors": ["Beta", "V", "VI", "VIII"], "reflector": "Thin-C",
              "rings": "EPEL", "positions": "CDSZ",
              "plugs": "AE BF CM DQ HU JN LX PR SZ VW"},
             "KRKRALLEXXFOLGENDESISTSOFORTBEKANNTZUGEBEN")


def _random_cfg(rng, m4):
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if m4:
        greek = rng.choice(["Beta", "Gamma"])
        refl = rng.choice(["Thin-B", "Thin-C"])
        pool = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
        wheels = [greek] + rng.sample(pool, 3)
        n = 4
    else:
        pool = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
        wheels = rng.sample(pool, 3)
        refl = rng.choice(["B", "C"])
        n = 3
    # штекеры: случайное число пар 0..10 без повторов букв
    bag = list(letters)
    rng.shuffle(bag)
    npairs = rng.randint(0, 10)
    plugs = " ".join("".join(bag[2 * i:2 * i + 2]) for i in range(npairs))
    return {"model": "M4" if m4 else "M3", "rotors": wheels,
            "reflector": refl,
            "rings": "".join(rng.choice(letters) for _ in range(n)),
            "positions": "".join(rng.choice(letters) for _ in range(n)),
            "plugs": plugs}


def test_random_differential_m3(seed=20260920, count=40):
    rng = random.Random(seed)
    for i in range(count):
        cfg = _random_cfg(rng, m4=False)
        # длинные тексты: многократные обороты + double-step зоны
        text = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                       for _ in range(rng.choice([5, 50, 300])))
        try:
            _compare(cfg, text)
        except AssertionError as ex:
            raise AssertionError(f"[case {i}] {ex}") from None


def test_random_differential_m4(seed=20260921, count=40):
    rng = random.Random(seed)
    for i in range(count):
        cfg = _random_cfg(rng, m4=True)
        text = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
                       for _ in range(rng.choice([5, 50, 300])))
        try:
            _compare(cfg, text)
        except AssertionError as ex:
            raise AssertionError(f"[case {i}] {ex}") from None
