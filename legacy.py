#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Загрузчик файлов машин от симулятора Enigma 1.x (Rijmenants/Weierud).

Формат: Order = 4 символа слева направо (цифры 1-8 -> I-VIII,
B -> Beta, C -> Gamma). Профиль M3 использует последние 3 символа.
Профиль Abwehr (G): первый символ — селектор UKW, далее 3 колеса;
позиции/кольца UKW берутся из секции [UKW].
UKW Select B/C -> толстый (M3) или тонкий (M4) рефлектор.
Steckers Matrix -> 26-буквенная подстановка, пары выводятся из неё.
"""
from __future__ import annotations

import os

from enigma import EnigmaCommercial, EnigmaG, EnigmaMachine

DIGITS = {"1": "I", "2": "II", "3": "III", "4": "IV",
          "5": "V", "6": "VI", "7": "VII", "8": "VIII",
          "B": "Beta", "C": "Gamma"}


def matrix_to_plugs(matrix: str) -> str:
    matrix = matrix.strip().upper()
    pairs: list[str] = []
    seen: set[str] = set()
    for i, ch in enumerate(matrix):
        a = chr(65 + i)
        if ch != a and a not in seen:
            pairs.append(a + ch)
            seen.add(a)
            seen.add(ch)
    return " ".join(pairs)


def load_machine(path: str):
    vals: dict[str, str] = {}
    section = ""
    skin = ""
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                continue
            if "=" in line and not line.startswith(("|", "#")):
                k, v = line.split("=", 1)
                k = k.strip().lower()
                vals[section + "." + k] = v.strip()
                if k == "skin":
                    skin = v.strip()
    profile = vals.get(".profile", "M3").upper()
    if profile == "ABWEHR":
        # Order = [UKW-sel, L, M, R], напр. "1321" -> колёса III II I.
        # Позиции/кольца UKW — из секции [UKW], колёс — последние 3 буквы.
        order = vals["rotors.order"]
        wheels = [DIGITS[c] for c in order[1:]]
        variant = "G312" if "312" in skin else ("G260" if "260" in skin else "G")
        rings = vals["ukw.ring"] + vals["rotors.rings"][1:]
        start = vals["ukw.start"] + vals["rotors.start"][1:]
        return EnigmaG(variant, tuple(wheels), rings, start)
    is_m4 = profile == "M4"
    order = [DIGITS[c] for c in vals["rotors.order"]]
    rings = vals["rotors.rings"]
    start = vals["rotors.start"]
    ukw = vals["ukw.select"]
    refl = ("Thin-" if is_m4 else "") + ukw
    plugs = matrix_to_plugs(vals.get("steckers.matrix", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    if not is_m4:
        order, rings, start = order[-3:], rings[-3:], start[-3:]
    return EnigmaMachine(tuple(order), refl, rings, start, plugs)


def read_groups(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return "".join(c for c in f.read().upper() if "A" <= c <= "Z")


if __name__ == "__main__":
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Examples")

    # DoubleStep: позиции окон после 6 нажатий
    m = load_machine(os.path.join(base, "DoubleStep", "M4_ADO"))
    seq = [m.positions[1:]]
    for _ in range(6):
        m.press("A")
        seq.append(m.positions[1:])
    print("DoubleStep:", seq)
    assert seq == ["ADO", "ADP", "ADQ", "AER", "BFS", "BFT", "BFU"], seq

    # Notches M4: 10 нажатий из NZAM
    m = load_machine(os.path.join(base, "Notches", "M4_NZAM"))
    seq = [m.positions]
    for _ in range(10):
        m.press("A")
        seq.append(m.positions)
    print("Notches M4:", seq)
    assert seq == ["NZAM", "NZAN", "NZAO", "NZAP", "NZAQ", "NZBR",
                   "NZBS", "NZBT", "NZBU", "NZBV", "NZBW"], seq

    # Notches G312: 10 нажатий из NZAM (шестерёночный carry-шаг + Lobster)
    mg = load_machine(os.path.join(base, "Notches", "G_NZAM"))
    seq = [mg.positions]
    for _ in range(10):
        mg.press("A")
        seq.append(mg.positions)
    print("Notches G312:", seq)
    assert seq == ["NZAM", "NZAN", "NZAO", "NABP", "NACQ", "OBDR",
                   "OBDS", "OCET", "OCEU", "OCFV", "ODGW"], seq

    # Wetter: M3 и M4 в совместимом режиме дают одинаковый шифр
    m3 = load_machine(os.path.join(base, "Wetter", "M3"))
    m4 = load_machine(os.path.join(base, "Wetter", "M4"))
    probe = "WETTERBERICHT"
    c3, c4 = m3.encipher(probe), m4.encipher(probe)
    print("Wetter M3:", c3, " M4:", c4)
    assert c3 == c4, (c3, c4)

    # Dönitz: индикатор HRQNSMAD при старте -> ключ, затем расшифровка
    dd = [d for d in os.listdir(base)
          if os.path.isdir(os.path.join(base, d)) and d not in
          ("DoubleStep", "Notches", "Wetter")][0]
    setup = load_machine(os.path.join(base, dd, "Setup"))
    initial = read_groups(os.path.join(base, dd, "Initial"))
    key = setup.decipher(initial)
    print("Doenitz indicator:", initial, "->", key)
    assert key[:4] == key[4:] == "ASTV", key
    setup2 = load_machine(os.path.join(base, dd, "Setup"))
    setup2.reset()
    for r, ch in zip(setup2.rotors, "ASTV"):
        r.pos = ord(ch) - 65
    msg = read_groups(os.path.join(base, dd, "Message"))
    # последние 8 букв — повтор индикатора, не входят в текст
    plain = setup2.decipher(msg[:-8] if msg.endswith(initial) else msg)
    print("Doenitz plain:", plain)
    assert plain == "DERFUEHRERISTTOTXDERKAMPFGEHTWEITERXDOENITZX", plain

    print("EXAMPLES ALL OK")
