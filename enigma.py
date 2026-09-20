#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Enigma I / M3 / M4 / G / K / D — шифрование и дешифровка сообщений.

M-line (рычажный шаг, двойной шаг среднего ротора, ETW = алфавит):
  Enigma I  (Heer/Luftwaffe): 3 ротора из I–V, UKW A/B/C, штекеры.
  Enigma M3 (Kriegsmarine):   3 ротора из I–VIII, UKW B/C, штекеры.
  Enigma M4 (U-Boat):         греческий Beta/Gamma (статичен) + 3 ротора
                              из I–VIII, тонкие UKW Thin-B/Thin-C, штекеры.

Enigma G (Abwehr, Zählwerk):  3 колеса I–III (3 варианта проводок),
  подвижный UKW с кольцом, ETW = QWERTZ, БЕЗ штекеров,
  шестерёночный carry-шаг без двойного шага (проверен таблицей из
  Examples/Notches: NZAM -> ... -> ODGW, включая Lobster на шаге 5).

Commercial K (A27) / D (A26): 3 колеса коммерческой проводки, settable
  неподвижный UKW с кольцом, ETW = QWERTZ, БЕЗ штекеров, обычный
  рычажный шаг. Engagement: K = Y/E/N; D = notch на корпусе
  (engagement = Y + ring).

Enigma симметрична: расшифровка = шифровка при тех же настройках.

Проводки: NSA wiring catalog (Hammarborg/Weierud), cryptomuseum,
Hamer, Toledo enigma_configs.py. G-turnover колонки = engagement-окна
(подтверждено G-111 doc + таблицей Notches).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
A_ORD = ord("A")


def _c2i(c: str) -> int:
    return ord(c) - A_ORD


def _i2c(i: int) -> str:
    return chr(i % 26 + A_ORD)


# ---------------------------------------------------------------- M-line
# Проводка роторов. notch — окно engagement: если ротор показывает эту
# букву, на следующем нажатии шагает левый сосед.
ROTORS: dict[str, tuple[str, str]] = {
    "I":    ("EKMFLGDQVZNTOWYHXUSPAIBRCJ", "Q"),
    "II":   ("AJDKSIRUXBLHWTMCQGZNPYFVOE", "E"),
    "III":  ("BDFHJLCPRTXVZNYEIWGAKMUSQO", "V"),
    "IV":   ("ESOVPZJAYQUIRHXLNFTGKDCMWB", "J"),
    "V":    ("VZBRGITYUPSDNHLXAWMJQOFECK", "Z"),
    "VI":   ("JPGVOUMFYQBENHZRDKASXLICTW", "ZM"),
    "VII":  ("NZJHGRCXMYSWBOUFAIVLPEKQDT", "ZM"),
    "VIII": ("FKQHTLXOCBJSPDZRAMEWNIUYGV", "ZM"),
    # Греческие (M4, тонкие): без notch, не шагают
    "BETA":  ("LEYJVCNIXWPBQMDRTAKZGFUHOS", ""),
    "GAMMA": ("FSOKANUERHMBTIYCWLQPZXVGJD", ""),
}

# Рефлекторы. A (до лета 1937), B/C — толстые. Thin B/C — тонкие (M4).
REFLECTORS: dict[str, str] = {
    "A":      "EJMZALYXVBWFCRQUONTSPIKHGD",
    "B":      "YRUHQSLDPXNGOKMIEBFZCWVJAT",
    "C":      "FVPJIAOYEDRZXWGCTKUQSBNMHL",
    "THIN-B": "ENKQAUYWJICOPBLMDXZVFTHRGS",
    "THIN-C": "RDOBJNTKVEHMLFCWZAXGYIPSUQ",
}

_ETW_IDENTITY = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ETW_QWERTZ = "QWERTZUIOASDFGHJKPYXCVBNML"

# ------------------------------------------------------- Commercial K/D
# Коммерческая проводка (Ch 11 Tz 87 / Ch 15 Tz 69): та же у K и у G-default.
K_WHEELS: dict[str, str] = {
    "I":   "LPGSZMHAEOQKVXRFYBUTNICJDW",
    "II":  "SLVGBTFXJQOHEWIRZYAMKPCNDU",
    "III": "CJGDPSHKTURAWZXFMYNQOBVLIE",
}
K_UKW = "IMETCGFRAYSQBZXWLHKDVUPOJN"
K_ETW = _ETW_QWERTZ
# Engagement-окна K (notch на кольце; смещение рычага -8 от notch G/M/V).
K_ENGAGE: dict[str, set[int]] = {
    "I": {_c2i("Y")}, "II": {_c2i("E")}, "III": {_c2i("N")},
}
# D: notch на корпусе в точке G -> engagement-окно = Y + ring.
D_ENGAGE_BASE = _c2i("Y")

# ------------------------------------------------------------- Enigma G
G_ETW = _ETW_QWERTZ
# Позиции notch одинаковы для всех G (cryptomuseum); Turnover-колонки
# и есть engagement-окна (подтверждено таблицей Notches + G-111 doc).
G_ENGAGE: dict[str, set[int]] = {
    "I": {_c2i(c) for c in "SUVWZABCEFGIKLOPQ"},
    "II": {_c2i(c) for c in "STVYZACDFGHKMNQ"},
    "III": {_c2i(c) for c in "UWXAEFHKMNR"},
}
G_VARIANTS: dict[str, dict[str, str]] = {
    "G": {  # default = коммерческая (Ch 15 Tz 69/70)
        "I": "LPGSZMHAEOQKVXRFYBUTNICJDW",
        "II": "SLVGBTFXJQOHEWIRZYAMKPCNDU",
        "III": "CJGDPSHKTURAWZXFMYNQOBVLIE",
        "UKW": "IMETCGFRAYSQBZXWLHKDVUPOJN",
    },
    "G312": {  # Abwehr, serial 312 Bletchley Park (Ch 15 Tz 115 rewired UKW)
        "I": "DMTWSILRUYQNKFEJCAZBPGXOHV",
        "II": "HQZGPJTMOBLNCIFDYAWVEUSRKX",
        "III": "UQNTLSZFMREHDPXKIBVYGJCWOA",
        "UKW": "RULQMZJSYGOCETKWDAHNBXPVIF",
    },
    "G260": {  # Abwehr Аргентина (Ch 15 Tz 117/115)
        "I": "RCSPBLKQAUMHWYTIFZVGOJNEXD",
        "II": "WCMIBVPJXAROSGNDLZKEYHUFQT",
        "III": "FVDHZELSQMAXOKYIWPGCBUJTNR",
        "UKW": "IMETCGFRAYSQBZXWLHKDVUPOJN",
    },
}

# Алиасы имён рефлекторов (регистронезависимо, с/без дефиса)
_REFLECTOR_ALIASES = {
    "A": "A", "UKW-A": "A",
    "B": "B", "UKW-B": "B",
    "C": "C", "UKW-C": "C",
    "THIN-B": "THIN-B", "THINB": "THIN-B", "B-THIN": "THIN-B",
    "BTHIN": "THIN-B", "BRUNO": "THIN-B",
    "THIN-C": "THIN-C", "THINC": "THIN-C", "C-THIN": "THIN-C",
    "CTHIN": "THIN-C", "CAESAR": "THIN-C",
}

# Алиасы роторов
_ROTOR_ALIASES = {
    "BETA": "BETA", "B": "BETA",
    "GAMMA": "GAMMA", "G": "GAMMA",
    "I": "I", "II": "II", "III": "III", "IV": "IV",
    "V": "V", "VI": "VI", "VII": "VII", "VIII": "VIII",
    "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V",
    "6": "VI", "7": "VII", "8": "VIII",
}


# ------------------------------------------------- MachineSpec (AUD-002/003)
# Единый источник истины о размерности конфигураций. CLI, GUI и валидация
# базы обязаны брать defaults/размерности отсюда, а не из собственных
# жёстко заданных констант. wheels = число подвижных колёс; rings/positions =
# число букв Ringstellung/Grundstellung (у G первая буква = UKW).


@dataclass(frozen=True)
class MachineSpec:
    model: str
    wheels: int
    rings: int
    positions: int
    default_wheels: tuple[str, ...]
    default_reflector: str | None
    reflectors: tuple[str, ...]
    wheel_options: tuple[tuple[str, ...], ...]
    distinct_wheels: bool
    plugs: bool
    ukw_separate: bool  # K/D: отдельные pos/ring UKW помимо rings/positions


_M3_WHEELS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")
_I_WHEELS = ("I", "II", "III", "IV", "V")
_GKD_WHEELS = ("I", "II", "III")

MACHINE_SPECS: dict[str, MachineSpec] = {
    "I": MachineSpec("I", 3, 3, 3, ("I", "II", "III"), "A",
                     ("A", "B", "C"),
                     (_I_WHEELS,) * 3, False, True, False),
    "M3": MachineSpec("M3", 3, 3, 3, ("I", "II", "III"), "B",
                      ("B", "C"),
                      (_M3_WHEELS,) * 3, False, True, False),
    "M4": MachineSpec("M4", 4, 4, 4, ("Beta", "I", "II", "III"), "Thin-B",
                      ("Thin-B", "Thin-C"),
                      (("Beta", "Gamma"),) + (_M3_WHEELS,) * 3,
                      False, True, False),
    "G": MachineSpec("G", 3, 4, 4, ("I", "II", "III"), None, (),
                     (_GKD_WHEELS,) * 3, True, False, False),
    "G312": MachineSpec("G312", 3, 4, 4, ("I", "II", "III"), None, (),
                        (_GKD_WHEELS,) * 3, True, False, False),
    "G260": MachineSpec("G260", 3, 4, 4, ("I", "II", "III"), None, (),
                        (_GKD_WHEELS,) * 3, True, False, False),
    "K": MachineSpec("K", 3, 3, 3, ("I", "II", "III"), None, (),
                     (_GKD_WHEELS,) * 3, True, False, True),
    "D": MachineSpec("D", 3, 3, 3, ("I", "II", "III"), None, (),
                     (_GKD_WHEELS,) * 3, True, False, True),
}

ALL_MODELS: tuple[str, ...] = ("I", "M3", "M4", "G", "G312", "G260", "K", "D")


def spec_for(model: str) -> MachineSpec:
    """Spec модели по имени (регистронезависимо). Бросает ValueError."""
    key = (model or "").strip().upper()
    if key not in MACHINE_SPECS:
        raise ValueError(f"Неизвестная модель: {model!r}. "
                         f"Допустимы: {', '.join(ALL_MODELS)}")
    return MACHINE_SPECS[key]


def validate_dimensions(model: str, wheels: tuple[str, ...] | list[str],
                        rings: str, positions: str) -> None:
    """Проверить размерность конфигурации против MachineSpec.

    Формат ошибки — явный Expected/Received (требование AUD-006),
    данные не исправляются молча.
    """
    spec = spec_for(model)
    problems: list[str] = []
    if len(wheels) != spec.wheels:
        problems.append(f"Expected:\n{spec.wheels} wheels\n\nReceived:\n{len(wheels)}")
    if len(rings) != spec.rings:
        problems.append(f"Expected:\n{spec.rings} ring letters\n\nReceived:\n{len(rings)}")
    if len(positions) != spec.positions:
        problems.append(f"Expected:\n{spec.positions} position letters\n\nReceived:\n{len(positions)}")
    if spec.distinct_wheels and len(set(wheels)) != len(wheels):
        problems.append("Expected:\ndistinct wheels\n\nReceived:\n"
                        + " ".join(wheels))
    if problems:
        raise ValueError("Invalid machine configuration:\n\n"
                         f"machine: {spec.model}\n"
                         f"wheels: {' '.join(wheels)}\n"
                         f"rings: {rings}\n"
                         f"positions: {positions}\n\n"
                         + "\n\n".join(problems))


def normalize_rotor(name: str) -> str:
    key = name.strip().upper()
    if key not in _ROTOR_ALIASES:
        raise ValueError(f"Неизвестный ротор: {name!r}. Допустимы: I..VIII, Beta, Gamma")
    return _ROTOR_ALIASES[key]


def normalize_reflector(name: str) -> str:
    key = name.strip().upper().replace("_", "-").replace(" ", "-")
    if key not in _REFLECTOR_ALIASES:
        raise ValueError(
            f"Неизвестный рефлектор: {name!r}. "
            "Допустимы: A, B, C, Thin-B (Bruno), Thin-C (Caesar)"
        )
    return _REFLECTOR_ALIASES[key]


def parse_plugs(plugs: str) -> dict[int, int]:
    """'AB CD Ef' -> взаимные замены. Максимум 10 пар, без повторов."""
    board: dict[int, int] = {}
    if not plugs.strip():
        return board
    pairs = plugs.upper().split()
    if len(pairs) > 10:
        raise ValueError("Штекеров не может быть больше 10 пар")
    used: set[str] = set()
    for p in pairs:
        if len(p) != 2 or p[0] not in ALPHABET or p[1] not in ALPHABET:
            raise ValueError(f"Неверная пара штекеров: '{p}'. Пример: 'AB CD EF'")
        if p[0] == p[1]:
            raise ValueError(f"Нельзя соединять букву саму с собой: '{p}'")
        if p[0] in used or p[1] in used:
            raise ValueError(f"Буква используется дважды: '{p}'")
        used.add(p[0])
        used.add(p[1])
        board[_c2i(p[0])] = _c2i(p[1])
        board[_c2i(p[1])] = _c2i(p[0])
    return board


def _check_letters(s: str, n: int, what: str) -> str:
    s = s.upper().strip()
    if len(s) != n or any(c not in ALPHABET for c in s):
        raise ValueError(f"{what} — {n} буквы A-Z (напр. {'A' * n})")
    return s


class Rotor:
    """Один ротор с проводкой, кольцом, позицией и engagement-окнами."""

    def __init__(self, name: str, ring: int = 0, pos: int = 0,
                 wiring: str | None = None, notches: set[int] | None = None):
        if wiring is None:
            name = normalize_rotor(name)
            wiring_s, notch_s = ROTORS[name]
            self.name = name
            self._notches = {_c2i(c) for c in notch_s} if notches is None else set(notches)
            wiring = wiring_s
        else:
            self.name = name
            self._notches = set() if notches is None else set(notches)
        self.wiring = [_c2i(c) for c in wiring]
        self.inverse = [0] * 26
        for i, w in enumerate(self.wiring):
            self.inverse[w] = i
        self.ring = ring % 26
        self.pos = pos % 26

    def at_notch(self) -> bool:
        return self.pos in self._notches

    def step(self) -> None:
        self.pos = (self.pos + 1) % 26

    def forward(self, c: int) -> int:
        offset = self.pos - self.ring
        return (self.wiring[(c + offset) % 26] - offset) % 26

    def backward(self, c: int) -> int:
        offset = self.pos - self.ring
        return (self.inverse[(c + offset) % 26] - offset) % 26


class Reflector:
    """Рефлектор, возможно подвижный (G) и с кольцом."""

    def __init__(self, wiring: str, pos: int = 0, ring: int = 0):
        self.wiring = [_c2i(c) for c in wiring]
        self.pos = pos % 26
        self.ring = ring % 26

    def step(self) -> None:
        self.pos = (self.pos + 1) % 26

    def reflect(self, c: int) -> int:
        offset = self.pos - self.ring
        return (self.wiring[(c + offset) % 26] - offset) % 26


def _step_service_trio(left: Rotor, middle: Rotor, right: Rotor) -> None:
    """Рычажный шаг с двойным шагом среднего ротора (I/M3/M4/K/D)."""
    if middle.at_notch():
        middle.step()
        left.step()
    if right.at_notch():
        middle.step()
    right.step()


class EnigmaMachine:
    """Enigma I (роторы I–V, UKW A/B/C) / M3 (I–VIII, B/C) /
    M4 (Beta/Gamma + I–VIII, Thin-B/Thin-C). Рычажный шаг, штекеры."""

    def __init__(
        self,
        rotors: tuple[str, ...] = ("I", "II", "III"),
        reflector: str = "B",
        rings: str = "AAA",
        positions: str = "AAA",
        plugs: str = "",
        model: str | None = None,
        etw: str = _ETW_IDENTITY,
    ):
        if len(rotors) not in (3, 4):
            raise ValueError("Роторов должно быть 3 (I/M3) или 4 (M4)")
        self.is_m4 = len(rotors) == 4
        names = [normalize_rotor(r) for r in rotors]
        refl = normalize_reflector(reflector)
        if self.is_m4:
            if model is not None and model != "M4":
                raise ValueError(f"4 ротора — это M4, а не {model}")
            model = "M4"
            if names[0] not in ("BETA", "GAMMA"):
                raise ValueError("M4: левый (греческий) ротор должен быть Beta или Gamma")
            if refl in ("A", "B", "C"):
                raise ValueError("M4 требует тонкий рефлектор Thin-B или Thin-C")
        else:
            model = model or "M3"
            if model == "I":
                if any(n not in ("I", "II", "III", "IV", "V") for n in names):
                    raise ValueError("Enigma I: доступны только роторы I–V")
                if refl not in ("A", "B", "C"):
                    raise ValueError("Enigma I: рефлектор A, B или C (толстый)")
            elif model == "M3":
                if any(n not in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII")
                       for n in names):
                    raise ValueError("M3: доступны только роторы I–VIII")
                if refl not in ("B", "C"):
                    raise ValueError("M3: рефлектор B или C (толстый)")
            else:
                raise ValueError(f"Неизвестная модель M-line: {model!r}. Допустимы: I, M3, M4")
        if refl in ("THIN-B", "THIN-C") and not self.is_m4:
            raise ValueError("Тонкие рефлекторы Thin-B/Thin-C — только для M4 (4 ротора)")
        self.model_name = model

        n = len(rotors)
        rings = _check_letters(rings, n, "Кольца (rings)")
        positions = _check_letters(positions, n, "Позиции (positions)")
        if len(etw) != 26 or set(etw.upper()) != set(ALPHABET):
            raise ValueError("ETW — перестановка из 26 букв A-Z")

        self.rotors = [Rotor(nm, _c2i(r), _c2i(p))
                       for nm, r, p in zip(names, rings, positions)]
        self.reflector = Reflector(REFLECTORS[refl])
        self.reflector_name = refl
        self.plugboard = parse_plugs(plugs)
        self.etw = [_c2i(c) for c in etw.upper()]
        self.etw_inv = [0] * 26
        for i, w in enumerate(self.etw):
            self.etw_inv[w] = i
        self._initial = positions
        self.rotor_names = names

    @property
    def model(self) -> str:
        return self.model_name

    def reset(self) -> None:
        for r, c in zip(self.rotors, self._initial):
            r.pos = _c2i(c)

    @property
    def positions(self) -> str:
        return "".join(_i2c(r.pos) for r in self.rotors)

    def _step(self) -> None:
        movers = self.rotors if not self.is_m4 else self.rotors[1:]
        _step_service_trio(movers[0], movers[1], movers[2])

    def _plug(self, c: int) -> int:
        return self.plugboard.get(c, c)

    def press(self, ch: str) -> str:
        c = _c2i(ch)
        self._step()
        c = self._plug(c)
        c = self.etw[c]
        for rotor in reversed(self.rotors):
            c = rotor.forward(c)
        c = self.reflector.reflect(c)
        for rotor in self.rotors:
            c = rotor.backward(c)
        c = self.etw_inv[c]
        c = self._plug(c)
        return _i2c(c)

    def encipher(self, text: str) -> str:
        out: list[str] = []
        for ch in text.upper():
            if ch in ALPHABET:
                out.append(self.press(ch))
        return "".join(out)

    decipher = encipher


class EnigmaG:
    """Abwehr Enigma G (Zählwerk): колёса I–III (3 варианта проводок),
    подвижный UKW с кольцом, ETW = QWERTZ, без штекеров.
    Шестерёночный carry-шаг: правый всегда; средний — если правый в
    engagement-окне; левый — если средний шагнул И был в окне;
    UKW — если левый шагнул И был в окне. Двойного шага нет."""

    def __init__(
        self,
        variant: str = "G312",
        wheels: tuple[str, str, str] = ("I", "II", "III"),
        rings: str = "AAAA",
        positions: str = "AAAA",
    ):
        variant = variant.upper()
        if variant not in G_VARIANTS:
            raise ValueError(f"Неизвестный вариант G: {variant!r}. Допустимы: G, G312, G260")
        w = tuple(x.upper() for x in wheels)
        if len(w) != 3 or any(x not in ("I", "II", "III") for x in w):
            raise ValueError("Enigma G: 3 колеса I–III в любом порядке")
        if len(set(w)) != 3:
            raise ValueError("Enigma G: колёса не должны повторяться")
        rings = _check_letters(rings, 4, "Кольца G [UKW,L,M,R]")
        positions = _check_letters(positions, 4, "Позиции G [UKW,L,M,R]")
        data = G_VARIANTS[variant]
        self.variant = variant
        self.ukw = Reflector(data["UKW"], _c2i(positions[0]), _c2i(rings[0]))
        self.rotors = [Rotor(nm, _c2i(r), _c2i(p),
                             wiring=data[nm], notches=G_ENGAGE[nm])
                       for nm, r, p in zip(w, rings[1:], positions[1:])]
        self.etw = [_c2i(c) for c in G_ETW]
        self.etw_inv = [0] * 26
        for i, e in enumerate(self.etw):
            self.etw_inv[e] = i
        self._initial = positions
        self.wheel_names = list(w)

    @property
    def model(self) -> str:
        return "G-" + self.variant if self.variant != "G" else "G"

    def reset(self) -> None:
        self.ukw.pos = _c2i(self._initial[0])
        for r, c in zip(self.rotors, self._initial[1:]):
            r.pos = _c2i(c)

    @property
    def positions(self) -> str:
        return _i2c(self.ukw.pos) + "".join(_i2c(r.pos) for r in self.rotors)

    def _step(self) -> None:
        left, middle, right = self.rotors
        rb, mb, lb = right.pos, middle.pos, left.pos
        right.step()
        m_stepped = left_stepped = False
        if rb in G_ENGAGE[right.name]:
            middle.step()
            m_stepped = True
        if m_stepped and mb in G_ENGAGE[middle.name]:
            left.step()
            left_stepped = True
        if left_stepped and lb in G_ENGAGE[left.name]:
            self.ukw.step()

    def press(self, ch: str) -> str:
        c = _c2i(ch)
        self._step()
        c = self.etw[c]
        for rotor in reversed(self.rotors):
            c = rotor.forward(c)
        c = self.ukw.reflect(c)
        for rotor in self.rotors:
            c = rotor.backward(c)
        return _i2c(self.etw_inv[c])

    def encipher(self, text: str) -> str:
        out: list[str] = []
        for ch in text.upper():
            if ch in ALPHABET:
                out.append(self.press(ch))
        return "".join(out)

    decipher = encipher


class EnigmaCommercial:
    """Commercial K (A27) / D (A26): коммерческая проводка, settable
    неподвижный UKW с кольцом, ETW = QWERTZ, без штекеров, рычажный шаг.
    Engagement: K = Y/E/N (notch на кольце); D = notch на корпусе
    (engagement-окно = Y + ring)."""

    def __init__(
        self,
        model: str = "K",
        wheels: tuple[str, str, str] = ("I", "II", "III"),
        rings: str = "AAA",
        positions: str = "AAA",
        ukw_pos: str = "A",
        ukw_ring: str = "A",
    ):
        model = model.upper()
        if model not in ("K", "D"):
            raise ValueError(f"Неизвестная commercial-модель: {model!r}. Допустимы: K, D")
        w = tuple(x.upper() for x in wheels)
        if len(w) != 3 or any(x not in ("I", "II", "III") for x in w):
            raise ValueError("Commercial: 3 колеса I–III в любом порядке")
        if len(set(w)) != 3:
            raise ValueError("Commercial: колёса не должны повторяться")
        rings = _check_letters(rings, 3, "Кольца (rings)")
        positions = _check_letters(positions, 3, "Позиции (positions)")
        ukw_pos = _check_letters(ukw_pos, 1, "Позиция UKW")
        ukw_ring = _check_letters(ukw_ring, 1, "Кольцо UKW")
        self.model_name = model
        self.rotors = []
        for nm, r, p in zip(w, rings, positions):
            if model == "K":
                notch = K_ENGAGE[nm]
            else:
                notch = {(_c2i("Y") + _c2i(r)) % 26}
            self.rotors.append(Rotor(nm, _c2i(r), _c2i(p),
                                     wiring=K_WHEELS[nm], notches=notch))
        self.ukw = Reflector(K_UKW, _c2i(ukw_pos), _c2i(ukw_ring))
        self.etw = [_c2i(c) for c in K_ETW]
        self.etw_inv = [0] * 26
        for i, e in enumerate(self.etw):
            self.etw_inv[e] = i
        self._initial = positions
        self._ukw_initial = ukw_pos
        self.wheel_names = list(w)

    @property
    def model(self) -> str:
        return self.model_name

    def reset(self) -> None:
        for r, c in zip(self.rotors, self._initial):
            r.pos = _c2i(c)
        self.ukw.pos = _c2i(self._ukw_initial)

    @property
    def positions(self) -> str:
        return "".join(_i2c(r.pos) for r in self.rotors)

    def _step(self) -> None:
        _step_service_trio(self.rotors[0], self.rotors[1], self.rotors[2])

    def press(self, ch: str) -> str:
        c = _c2i(ch)
        self._step()
        c = self.etw[c]
        for rotor in reversed(self.rotors):
            c = rotor.forward(c)
        c = self.ukw.reflect(c)
        for rotor in self.rotors:
            c = rotor.backward(c)
        return _i2c(self.etw_inv[c])

    def encipher(self, text: str) -> str:
        out: list[str] = []
        for ch in text.upper():
            if ch in ALPHABET:
                out.append(self.press(ch))
        return "".join(out)

    decipher = encipher


def build_machine(args: argparse.Namespace):
    model = (args.model or "").upper() or None
    if model in (None, "I", "M3", "M4"):
        rotors = tuple(args.rotors)
        if model is None:
            model = "M4" if len(rotors) == 4 else "M3"
        spec = spec_for(model)
        # Defaults — из MachineSpec (AUD-003), явные значения уважаем.
        rings = args.rings if args.rings is not None else "A" * spec.rings
        positions = args.positions if args.positions is not None else "A" * spec.positions
        validate_dimensions(model, rotors, rings, positions)
        return EnigmaMachine(rotors=rotors, reflector=args.reflector,
                             rings=rings, positions=positions,
                             plugs=args.plugs, model=model)
    if model in ("G", "G312", "G260"):
        if args.plugs:
            raise ValueError("Enigma G без штекеров (Steckerbrett отсутствует)")
        spec = spec_for(model)
        wheels = tuple(args.rotors)
        rings = args.rings if args.rings is not None else "A" * spec.rings
        positions = args.positions if args.positions is not None else "A" * spec.positions
        validate_dimensions(model, wheels, rings, positions)
        return EnigmaG(variant=model, wheels=wheels,
                       rings=rings, positions=positions)
    if model in ("K", "D"):
        if args.plugs:
            raise ValueError("Commercial без штекеров (Steckerbrett отсутствует)")
        spec = spec_for(model)
        wheels = tuple(args.rotors)
        rings = args.rings if args.rings is not None else "A" * spec.rings
        positions = args.positions if args.positions is not None else "A" * spec.positions
        validate_dimensions(model, wheels, rings, positions)
        return EnigmaCommercial(model=model, wheels=wheels,
                                rings=rings, positions=positions,
                                ukw_pos=args.ukw_pos, ukw_ring=args.ukw_ring)
    raise ValueError(f"Неизвестная модель: {args.model!r}. "
                     "Допустимы: I, M3, M4, G, G312, G260, K, D")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Дешифратор Enigma I/M3/M4/G/K/D. Расшифровка = шифровка при тех же настройках.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  M3:  python enigma.py --model M3 --rotors I II III --reflector B\n"
            "         --rings AAA --positions AAA --text BDZGO\n"
            "  M4:  python enigma.py --model M4 --rotors Beta II IV I --reflector Thin-B\n"
            "         --rings AAAV --positions VJNA --plugs \"AT BL DF GJ HM NW OP QY RZ VX\"\n"
            "         --text \"NCZW VUSX ...\"\n"
            "  G:   python enigma.py --model G312 --rotors III II I\n"
            "         --rings AAAA --positions NZAM --text HELLO\n"
            "  K:   python enigma.py --model K --rotors I II III\n"
            "         --rings AAA --positions AAA --text HELLO\n"
        ),
    )
    p.add_argument("--model", default=None,
                   help="I, M3, M4, G, G312, G260, K, D (default: M4 при 4 роторах, иначе M3)")
    p.add_argument("--rotors", nargs="+", default=["I", "II", "III"],
                   help="M-line: 3 (I/M3) или 4 (M4, первый — Beta/Gamma). "
                        "G/K/D: 3 колеса I–III")
    p.add_argument("--reflector", default="B",
                   help="M-line: A/B/C (I), B/C (M3), Thin-B/Thin-C (M4)")
    p.add_argument("--rings", default=None,
                   help="Ringstellung (default из MachineSpec: M-line 3/4 буквы; G: 4 [UKW,L,M,R])")
    p.add_argument("--positions", default=None,
                   help="Startposition (default из MachineSpec: M-line 3/4 буквы; G: 4 [UKW,L,M,R])")
    p.add_argument("--plugs", default="", help="Штекеры M-line, напр. \"AB CD EF\"")
    p.add_argument("--ukw-pos", default="A", help="Позиция UKW (K/D)")
    p.add_argument("--ukw-ring", default="A", help="Кольцо UKW (K/D)")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Шифротекст одной строкой")
    group.add_argument("--in", dest="infile", help="Входной файл с шифротекстом")
    p.add_argument("--out", dest="outfile", help="Выходной файл (иначе stdout)")
    p.add_argument("--group5", action="store_true", help="Группировать вывод по 5")
    return p.parse_args(argv)


def format_groups(text: str, n: int = 5) -> str:
    return " ".join(text[i:i + n] for i in range(0, len(text), n))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        machine = build_machine(args)
    except ValueError as e:
        print(f"Ошибка настроек: {e}", file=sys.stderr)
        return 2
    cipher = args.text
    if cipher is None:
        try:
            with open(args.infile, encoding="utf-8") as f:
                cipher = f.read()
        except OSError as e:
            print(f"Не могу прочитать {args.infile}: {e}", file=sys.stderr)
            return 1
    plain = machine.decipher(cipher)
    if args.group5:
        plain = format_groups(plain)
    if args.outfile:
        try:
            with open(args.outfile, "w", encoding="utf-8") as f:
                f.write(plain + "\n")
        except OSError as e:
            print(f"Не могу записать {args.outfile}: {e}", file=sys.stderr)
            return 1
    else:
        print(plain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
