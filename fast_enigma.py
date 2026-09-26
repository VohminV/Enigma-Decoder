#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastEnigma, Phase 8 — быстрый evaluator массовых candidates.

НЕ замена reference core (enigma.py): математика не меняется, таблицы
генерируются ИЗ проверенных данных core (проводки/engagement-окна),
проверка — differential tests против reference.

Что убрано из hot loop (по аудиту hot path):
- construction на каждого candidate (~43 мкс, ~60% короткого sweep):
  таблицы строятся ОДИН раз, per-candidate только сброс позиций;
- ~12 method calls / ~25 attribute lookups на символ: один цикл на интах;
- per-char str/ord/chr/dict.get: вход str->ints один раз, plugboard/ETW —
  списки, выход ints->str один раз;
- `ch in ALPHABET` (substring search) на символ: фильтрация входа один раз.

Состояние инстанса: таблицы immutable после build; mutable — только позиции.
Один инстанс = один поток (как и reference). Отмена/потоки — снаружи.
"""
from __future__ import annotations

import enigma as _core


def encode_text(text: str) -> list[int]:
    """str -> ints (A=0..Z=25), не A-Z отбрасываются (как core.encipher)."""
    base = ord("A")
    return [ord(c) - base for c in text.upper() if "A" <= c <= "Z"]


def decode_ints(data) -> str:
    """ints -> str одним проходом."""
    return bytes(c + 65 for c in data).decode("ascii")


def _mask(windows) -> int:
    m = 0
    for w in windows:
        m |= 1 << w
    return m


def _tables(wiring: list[int], ring: int):
    """FWD/BWD[pos][c] для фиксированного кольца. 2×26×26 ints."""
    fwd = [[0] * 26 for _ in range(26)]
    bwd = [[0] * 26 for _ in range(26)]
    inv = [0] * 26
    for i, w in enumerate(wiring):
        inv[w] = i
    for p in range(26):
        off = p - ring
        fp, bp = fwd[p], bwd[p]
        for c in range(26):
            fp[c] = (wiring[(c + off) % 26] - off) % 26
            bp[c] = (inv[(c + off) % 26] - off) % 26
    return fwd, bwd


class FastEnigma:
    """Integer evaluator I/M3/M4/G/K/D. Таблицы из данных enigma.py."""

    def __init__(self, model: str, wheels: list[str], rings: str,
                 positions: str, reflector: str | None = None,
                 plugs: str = "", ukw_pos: str = "A",
                 ukw_ring: str = "A"):
        spec = _core.spec_for(model)
        _core.validate_dimensions(model, list(wheels), rings, positions)
        self.model = spec.model
        self._step_mode = "carry" if spec.model in ("G", "G312", "G260") else "lever"

        # --- колёса: таблицы + маски engagement-окон + кольца ---
        self._fwd: list = []
        self._bwd: list = []
        self._masks: list[int] = []
        self._pos: list[int] = []
        self._initial: list[int] = []
        if spec.model in ("I", "M3", "M4"):
            names = [_core.normalize_rotor(w) for w in wheels]
            for nm, rch in zip(names, rings):
                wiring_s, _ = _core.ROTORS[nm]
                wiring = [_core._c2i(c) for c in wiring_s]
                ring = _core._c2i(rch)
                f, b = _tables(wiring, ring)
                self._fwd.append(f)
                self._bwd.append(b)
                self._masks.append(_mask(
                    _core.Rotor(nm, ring, 0)._notches))
            refl = _core.normalize_reflector(reflector or spec.default_reflector or "B")
            # Совместимость модель/рефлектор — как core (иначе молчаливое
            # расхождение с reference на невалидных конфигах).
            if len(names) == 4:
                if names[0] not in ("BETA", "GAMMA"):
                    raise ValueError("M4: левый ротор должен быть Beta или Gamma")
                if refl in ("A", "B", "C"):
                    raise ValueError("M4 требует тонкий рефлектор Thin-B/Thin-C")
            elif spec.model == "I":
                if any(n not in ("I", "II", "III", "IV", "V") for n in names):
                    raise ValueError("Enigma I: только роторы I–V")
                if refl not in ("A", "B", "C"):
                    raise ValueError("Enigma I: рефлектор A, B или C")
            elif spec.model == "M3":
                if refl not in ("B", "C"):
                    raise ValueError("M3: рефлектор B или C")
            self._ukw = [_core._c2i(c) for c in _core.REFLECTORS[refl]]
            self._ukw_pos = 0
            self._ukw_ring = 0
            self._ukw_moves = False
            self._etw = None
            # M4: греческий (индекс 0) статичен — вне movers
            self._movers = list(range(len(names))) if len(names) == 3 else [1, 2, 3]
        elif spec.model in ("G", "G312", "G260"):
            data = _core.G_VARIANTS[spec.model]
            wnames = [w.upper() for w in wheels]
            if len(set(wnames)) != 3 or any(w not in ("I", "II", "III") for w in wnames):
                raise ValueError("Enigma G: 3 разных колеса I–III")
            self._ukw = [_core._c2i(c) for c in data["UKW"]]
            self._ukw_ring = _core._c2i(rings[0])
            self._ukw_pos = _core._c2i(positions[0])
            self._ukw_initial = self._ukw_pos
            self._ukw_moves = True
            for nm, rch in zip(wnames, rings[1:]):
                wiring = [_core._c2i(c) for c in data[nm]]
                f, b = _tables(wiring, _core._c2i(rch))
                self._fwd.append(f)
                self._bwd.append(b)
                self._masks.append(_mask(_core.G_ENGAGE[nm]))
            self._movers = [0, 1, 2]
            etw = [_core._c2i(c) for c in _core.G_ETW]
            inv = [0] * 26
            for i, e in enumerate(etw):
                inv[e] = i
            self._etw = (etw, inv)
        else:  # K/D
            self._ukw = [_core._c2i(c) for c in _core.K_UKW]
            self._ukw_ring = _core._c2i(ukw_ring)
            self._ukw_pos = _core._c2i(ukw_pos)
            self._ukw_initial = self._ukw_pos
            self._ukw_moves = False
            wnames = [w.upper() for w in wheels]
            if len(set(wnames)) != 3 or any(w not in ("I", "II", "III") for w in wnames):
                raise ValueError("Commercial: 3 разных колеса I–III")
            for nm, rch in zip(wnames, rings):
                wiring = [_core._c2i(c) for c in _core.K_WHEELS[nm]]
                ring = _core._c2i(rch)
                f, b = _tables(wiring, ring)
                self._fwd.append(f)
                self._bwd.append(b)
                if spec.model == "K":
                    self._masks.append(_mask(_core.K_ENGAGE[nm]))
                else:
                    self._masks.append(_mask(
                        {(_core.D_ENGAGE_BASE + ring) % 26}))
            self._movers = [0, 1, 2]
            etw = [_core._c2i(c) for c in _core.K_ETW]
            inv = [0] * 26
            for i, e in enumerate(etw):
                inv[e] = i
            self._etw = (etw, inv)
            # UKW неподвижен весь прогон: сворачиваем offset в таблицу один раз
            uoff = self._ukw_pos - self._ukw_ring
            ukw_tab = self._ukw
            self._uk_static = [(ukw_tab[(c + uoff) % 26] - uoff) % 26
                               for c in range(26)]

        self._plug = list(range(26))
        for a, b in _core.parse_plugs(plugs).items():
            self._plug[a] = b
        if spec.model in ("G", "G312", "G260"):
            self._wheel_initial = [_core._c2i(c) for c in positions[1:]]
        else:
            self._wheel_initial = [_core._c2i(c) for c in positions]
        self._pos = list(self._wheel_initial)
        self._n = len(self._fwd)

    @classmethod
    def from_config(cls, cfg: dict) -> "FastEnigma":
        """services-style cfg: model/rotors/reflector/rings/positions/
        plugs/ukw_pos/ukw_ring."""
        return cls(cfg["model"], list(cfg["rotors"]), cfg["rings"],
                   cfg["positions"], cfg.get("reflector"),
                   cfg.get("plugs", ""), cfg.get("ukw_pos", "A"),
                   cfg.get("ukw_ring", "A"))

    def reset(self) -> None:
        self._pos = list(self._wheel_initial)
        if self._ukw_moves:
            self._ukw_pos = self._ukw_initial

    def set_positions(self, positions: str) -> None:
        """Только сброс позиций (дешёвый per-candidate setup)."""
        if self.model in ("G", "G312", "G260"):
            if len(positions) != 4:
                raise ValueError("G positions: 4 буквы [UKW,L,M,R]")
            if any(not ("A" <= c <= "Z") for c in positions):
                raise ValueError(f"Некорректные позиции G: {positions!r}. Только A-Z.")
            self._ukw_pos = ord(positions[0]) - 65
            self._pos = [ord(c) - 65 for c in positions[1:]]
        else:
            if len(positions) != self._n:
                raise ValueError("positions length mismatch")
            if any(not ("A" <= c <= "Z") for c in positions):
                raise ValueError(f"Некорректные позиции: {positions!r}. Только A-Z.")
            self._pos = [ord(c) - 65 for c in positions]

    @property
    def positions(self) -> str:
        s = "".join(chr(p + 65) for p in self._pos)
        if self.model in ("G", "G312", "G260"):
            return chr(self._ukw_pos + 65) + s
        return s

    # -- stepping --
    def _step_lever(self) -> None:
        l, m, r = (self._pos[i] for i in self._movers)
        mm, rm = self._masks[self._movers[1]], self._masks[self._movers[2]]
        if (mm >> m) & 1:
            m = (m + 1) % 26
            l = (l + 1) % 26
        if (rm >> r) & 1:
            m = (m + 1) % 26
        r = (r + 1) % 26
        self._pos[self._movers[0]] = l
        self._pos[self._movers[1]] = m
        self._pos[self._movers[2]] = r

    def _step_carry(self) -> None:
        lp, mp, rp = self._pos
        lm, mm, rm = self._masks
        rp = (rp + 1) % 26
        m_stepped = l_stepped = False
        if (rm >> self._pos[2]) & 1:
            mp = (mp + 1) % 26
            m_stepped = True
        if m_stepped and ((mm >> self._pos[1]) & 1):
            lp = (lp + 1) % 26
            l_stepped = True
        if l_stepped and ((lm >> self._pos[0]) & 1):
            self._ukw_pos = (self._ukw_pos + 1) % 26
        self._pos = [lp, mp, rp]

    # -- signal path --
    def decrypt_ints(self, data) -> list[int]:
        """Ints in -> ints out. Stepping ПЕРЕД символом (как core)."""
        if self._step_mode == "lever":
            return self._decrypt_lever(data)
        return self._decrypt_carry(data)

    def _decrypt_lever(self, data) -> list[int]:
        # Рычажный шаг заинлайнен (без per-char method call); таблицы,
        # маски и позиции — локальные переменные. Movers — последние 3
        # ротора (M4: греческий статичен, но участвует в тракте).
        fwd, bwd, plug = self._fwd, self._bwd, self._plug
        n = self._n
        i0, i1, i2 = n - 3, n - 2, n - 1
        F0, F1, F2 = fwd[i0], fwd[i1], fwd[i2]
        B0, B1, B2 = bwd[i0], bwd[i1], bwd[i2]
        m1, m2 = self._masks[i1], self._masks[i2]
        p0, p1, p2 = self._pos[i0], self._pos[i1], self._pos[i2]
        etw = self._etw
        out = []
        append = out.append
        if etw is None:
            ukw = self._ukw
            if n == 3:
                for c in data:
                    if (m1 >> p1) & 1:
                        p1 += 1
                        p0 += 1
                        if p1 == 26:
                            p1 = 0
                        if p0 == 26:
                            p0 = 0
                    if (m2 >> p2) & 1:
                        p1 += 1
                        if p1 == 26:
                            p1 = 0
                    p2 += 1
                    if p2 == 26:
                        p2 = 0
                    c = plug[c]
                    c = F2[p2][c]
                    c = F1[p1][c]
                    c = F0[p0][c]
                    c = ukw[c]
                    c = B0[p0][c]
                    c = B1[p1][c]
                    c = B2[p2][c]
                    append(plug[c])
            else:  # M4: + статичный греческий тракт (индекс 0)
                Fg, Bg = fwd[0], bwd[0]
                pg = self._pos[0]
                for c in data:
                    if (m1 >> p1) & 1:
                        p1 += 1
                        p0 += 1
                        if p1 == 26:
                            p1 = 0
                        if p0 == 26:
                            p0 = 0
                    if (m2 >> p2) & 1:
                        p1 += 1
                        if p1 == 26:
                            p1 = 0
                    p2 += 1
                    if p2 == 26:
                        p2 = 0
                    c = plug[c]
                    c = F2[p2][c]
                    c = F1[p1][c]
                    c = F0[p0][c]
                    c = Fg[pg][c]
                    c = ukw[c]
                    c = Bg[pg][c]
                    c = B0[p0][c]
                    c = B1[p1][c]
                    c = B2[p2][c]
                    append(plug[c])
        else:
            ein, einv = etw
            uk = self._uk_static
            for c in data:
                if (m1 >> p1) & 1:
                    p1 += 1
                    p0 += 1
                    if p1 == 26:
                        p1 = 0
                    if p0 == 26:
                        p0 = 0
                if (m2 >> p2) & 1:
                    p1 += 1
                    if p1 == 26:
                        p1 = 0
                p2 += 1
                if p2 == 26:
                    p2 = 0
                c = ein[c]
                c = F2[p2][c]
                c = F1[p1][c]
                c = F0[p0][c]
                c = uk[c]
                c = B0[p0][c]
                c = B1[p1][c]
                c = B2[p2][c]
                append(einv[c])
        self._pos[i0], self._pos[i1], self._pos[i2] = p0, p1, p2
        return out

    def _decrypt_carry(self, data) -> list[int]:
        """Шестерёночный carry-шаг G (не hot path cracker — ясно и просто)."""
        fwd, bwd = self._fwd, self._bwd
        ukw = self._ukw
        n = self._n
        ein, einv = self._etw
        ukw_ring = self._ukw_ring
        out = []
        append = out.append
        for c in data:
            self._step_carry()
            pos = self._pos
            up = self._ukw_pos
            c = ein[c]
            c = fwd[n - 1][pos[n - 1]][c]
            for i in range(n - 2, -1, -1):
                c = fwd[i][pos[i]][c]
            c = (ukw[(c + up - ukw_ring) % 26] - (up - ukw_ring)) % 26
            for i in range(n):
                c = bwd[i][pos[i]][c]
            append(einv[c])
        return out

    def decrypt(self, text: str) -> str:
        """str in -> str out (фильтрация не A-Z как core.encipher)."""
        return decode_ints(self.decrypt_ints(encode_text(text)))

    decipher = decrypt
