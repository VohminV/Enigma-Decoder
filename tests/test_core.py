#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit-тесты EnigmaCore: свойства компонентов без внешних векторов.
Источники констант:
  notch/проводки M-line — Hamer, NSA wiring catalog (Hammarborg/Weierud);
  UKW-A — Hamer (EJMZALYXVBWFCRQUONTSPIKHGD);
  G engagement-колонки — cryptomuseum wiring.htm + G-111 doc
    (turnover-письмо в окне => шаг соседа на следующем нажатии),
    сверены с Examples/Notches таблицей;
  K engagement Y/E/N — cryptomuseum wiring.htm (notch G/M/V минус
    смещение рычага 8: G-8=Y, M-8=E, V-8=N; как у service I: Y-8=Q).
Запуск: python test_core.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from enigma import (  # noqa: E402
    D_ENGAGE_BASE,
    G_ENGAGE,
    K_ENGAGE,
    K_ETW,
    K_WHEELS,
    REFLECTORS,
    ROTORS,
    EnigmaCommercial,
    EnigmaG,
    EnigmaMachine,
    _c2i,
    parse_plugs,
)

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"[OK] {name}")
    else:
        failed += 1
        print(f"[FAIL] {name}")


# --- 1. notch-позиции M-line (engagement-окна) ---
check("notch I-V", [{k: ROTORS[k][1] for k in ("I", "II", "III", "IV", "V")}
                    == {"I": "Q", "II": "E", "III": "V", "IV": "J", "V": "Z"}][0])
check("notch VI-VIII double", all(ROTORS[k][1] == "ZM" for k in ("VI", "VII", "VIII")))
check("greek no notch", ROTORS["BETA"][1] == "" and ROTORS["GAMMA"][1] == "")

# --- 2. рефлекторы — инволюция W[W[i]] == i ---
for name, wiring in REFLECTORS.items():
    w = [_c2i(c) for c in wiring]
    check(f"reflector {name} involution", all(w[w[i]] == i for i in range(26)))

# --- 3. plugboard: разбор и ошибки ---
check("plugs parse", parse_plugs("AB cd EF") == {0: 1, 1: 0, 2: 3, 3: 2, 4: 5, 5: 4})
for bad in ("AA", "AB BC", "A", "ABC", "AB CD EF GH IJ KL MN OP QR ST UV"):
    try:
        parse_plugs(bad)
        check(f"plugs reject {bad!r}", False)
    except ValueError:
        check(f"plugs reject {bad!r}", True)
check("plugs empty", parse_plugs("  ") == {})

# --- 4. ringstellung влияет; позиции влияют ---
a = EnigmaMachine(("I", "II", "III"), "B", "AAA", "AAA", model="M3")
b = EnigmaMachine(("I", "II", "III"), "B", "AAB", "AAA", model="M3")
check("rings matter", a.encipher("AAAAA") != b.encipher("AAAAA"))
c = EnigmaMachine(("I", "II", "III"), "B", "AAA", "AAB", model="M3")
a2 = EnigmaMachine(("I", "II", "III"), "B", "AAA", "AAA", model="M3")
check("positions matter", a2.encipher("AAAAA") != c.encipher("AAAAA"))

# --- 5. reset / воспроизводимость ---
m = EnigmaMachine(("IV", "V", "VI"), "C", "BQE", "QWE", "AB CD", model="M3")
first = m.encipher("NACHRICHT" * 10)
check("state advances", m.positions != "QWE")
m.reset()
check("reset restores", m.positions == "QWE" and m.encipher("NACHRICHT" * 10) == first)

# --- 6. double-step: ADQ -> AER -> BFS (роторы III II I) ---
m = EnigmaMachine(("III", "II", "I"), "B", "AAA", "ADQ", model="M3")
seq = [m.positions]
for _ in range(2):
    m.press("A")
    seq.append(m.positions)
check("double-step ADQ/AER/BFS", seq == ["ADQ", "AER", "BFS"])

# --- 7. decrypt(enc) == msg; буква никогда не шифруется в себя ---
def _m3():
    return EnigmaMachine(("V", "II", "VIII"), "C", "EPE", "NAE",
                         "AE BF CM DQ HU JN LX PR SZ VW", model="M3")


for text in ("ANGRIFFUMNULLUHR", "X" * 50, "QWERTZUIOASDFGHJKPYXCVBNML"):
    enc = _m3().encipher(text)
    dec = _m3().decipher(enc)
    check(f"roundtrip {text[:12]}", dec == text)
mm = EnigmaMachine(("I", "II", "III"), "B", "AAA", "AAA", model="M3")
ok_self = True
for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    mm.reset()
    if mm.press(ch) == ch:
        ok_self = False
check("never self-encrypts", ok_self)

# --- 8. M4: греческий ротор статичен ---
m4 = EnigmaMachine(("Beta", "II", "IV", "I"), "Thin-B", "AAAV", "VJNA",
                   "AT BL DF GJ HM NW OP QY RZ VX")
m4.encipher("A" * 500)
check("greek static", m4.positions[0] == "V")

# --- 9. G engagement-колонки (17/15/11) ---
check("G engage sizes", {k: len(v) for k, v in G_ENGAGE.items()}
      == {"I": 17, "II": 15, "III": 11})
check("G engage III", G_ENGAGE["III"] == {_c2i(c) for c in "UWXAEFHKMNR"})

# --- 10. K engagement + ETW; D сдвиг с кольцом ---
check("K engage", K_ENGAGE == {"I": {_c2i("Y")}, "II": {_c2i("E")}, "III": {_c2i("N")}})
check("K ETW permutation", sorted(K_ETW) == sorted("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
check("K wheels == G default", all(
    K_WHEELS[k] == v for k, v in
    {"I": "LPGSZMHAEOQKVXRFYBUTNICJDW",
     "II": "SLVGBTFXJQOHEWIRZYAMKPCNDU",
     "III": "CJGDPSHKTURAWZXFMYNQOBVLIE"}.items()))
d_a = EnigmaCommercial("D", ("I", "II", "III"), "AAA", "AAA")
d_b = EnigmaCommercial("D", ("I", "II", "III"), "BBB", "AAA")
check("D body-notch shifts", (d_a.rotors[0]._notches == {D_ENGAGE_BASE}
                              and d_b.rotors[0]._notches == {(D_ENGAGE_BASE + 1) % 26}))
# G/K/D без штекеров: press работает без plugboard
EnigmaG("G312", ("I", "II", "III"), "AAAA", "AAAA").press("A")
EnigmaCommercial("K", ("I", "II", "III"), "AAA", "AAA").press("A")
check("G/K no-plugboard path", True)

print(f"CORE: passed={passed} failed={failed}")
sys.exit(0 if failed == 0 else 1)
