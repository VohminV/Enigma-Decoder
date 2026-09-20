#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application Services — тонкий слой между GUI и ядром.

Здесь НЕТ Qt и НЕТ математики роторов: только сборка конфигураций,
вызовы EnigmaCore / KeyDatabase и замеры. GUI импортирует только
этот модуль (и keydb через него).
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keydb  # noqa: E402
from enigma import (EnigmaCommercial, EnigmaG, EnigmaMachine,  # noqa: E402
                    MACHINE_SPECS, spec_for)

# Метаданные моделей для комбобоксов. Структура/размерности — из
# enigma.MachineSpec (единый источник истины, AUD-002); здесь только
# GUI-ярлыки. rotors: варианты для каждой позиции слева направо.
_MACHINE_LABELS = {
    "I": "Enigma I (Heer)",
    "M3": "Enigma M3 (Kriegsmarine)",
    "M4": "Enigma M4 (U-Boat)",
    "G312": "Enigma G312 (Abwehr)",
    "G260": "Enigma G260 (Abwehr)",
    "G": "Enigma G (default)",
    "K": "Commercial K (A27)",
    "D": "Commercial D (A26)",
}
_G_VARIANTS = {"G": "G", "G312": "G312", "G260": "G260"}

MACHINE_MODELS: dict[str, dict] = {}
for _key, _spec in MACHINE_SPECS.items():
    MACHINE_MODELS[_key] = {
        "label": _MACHINE_LABELS[_key],
        "rotors": [list(o) for o in _spec.wheel_options],
        "reflectors": list(_spec.reflectors),
        "plugs": _spec.plugs,
        # отдельный UKW-блок pos/ring — только K/D; у G UKW — первая
        # буква rings/positions (4 бокса, первый = UKW).
        "ukw": _spec.ukw_separate,
        "greek": _key == "M4",
        "rings": _spec.rings,
        "positions": _spec.positions,
    }
    if _key in _G_VARIANTS:
        MACHINE_MODELS[_key]["variant"] = _G_VARIANTS[_key]
del _key, _spec

LANGUAGES = ["German", "English"]


def build_machine(cfg: dict):
    """Собрать движок из конфига GUI. cfg: model, rotors[], reflector,
    rings (буквы), positions (буквы), plugs, ukw_pos, ukw_ring.
    Бросает ValueError с понятным текстом."""
    model = cfg["model"]
    if model in ("I", "M3", "M4"):
        return EnigmaMachine(tuple(cfg["rotors"]), cfg.get("reflector", "B"),
                             cfg.get("rings", "A" * len(cfg["rotors"])),
                             cfg.get("positions", "A" * len(cfg["rotors"])),
                             cfg.get("plugs", ""), model=model)
    if model in ("G", "G312", "G260"):
        meta = MACHINE_MODELS[model]
        return EnigmaG(meta["variant"], tuple(cfg["rotors"]),
                       cfg.get("rings", "AAAA"), cfg.get("positions", "AAAA"))
    if model in ("K", "D"):
        return EnigmaCommercial(model, tuple(cfg["rotors"]),
                                cfg.get("rings", "AAA"), cfg.get("positions", "AAA"),
                                cfg.get("ukw_pos", "A"), cfg.get("ukw_ring", "A"))
    raise ValueError(f"Неизвестная модель: {model!r}")


def process_text(cfg: dict, text: str) -> str:
    """Шифровка = расшифровка при тех же настройках."""
    return build_machine(cfg).decipher(text)


def default_config(model: str = "M3") -> dict:
    """Дефолтный конфиг из MachineSpec (AUD-002/003): корректная
    размерность и колёса без дублей для всех 8 моделей."""
    spec = spec_for(model)
    cfg = {"model": model, "rotors": list(spec.default_wheels),
           "rings": "A" * spec.rings, "positions": "A" * spec.positions,
           "plugs": "", "ukw_pos": "A", "ukw_ring": "A"}
    if spec.default_reflector is not None:
        cfg["reflector"] = spec.default_reflector
    return cfg


def indicator_solve(cfg: dict, grundstellung: str, indicator: str) -> str:
    """Восстановить ключ сообщения: расшифровать индикатор на Grundstellung."""
    cfg = dict(cfg)
    cfg["positions"] = grundstellung.upper().strip()
    return build_machine(cfg).decipher(indicator)


# --- KeyDatabase passthrough ---
def db_entries(db_path: str | None = None) -> list[dict]:
    return keydb.load_db(db_path) if db_path else keydb.load_db()


def search_entries(entries: list[dict], date_from: str, date_to: str, machine: str) -> list[dict]:
    out = []
    for e in entries:
        if e["date"] < date_from or e["date"] > date_to:
            continue
        if machine != "All" and e["model"] != machine:
            continue
        out.append(e)
    return out


def entry_machine_config(entry: dict, positions: str) -> dict:
    """Конфиг GUI-слоя для записи базы + заданных позиций."""
    n_wheels = len(entry["wheels"]) + (1 if entry.get("greek") else 0)
    cfg = {"model": entry["model"],
           "rotors": (([entry["greek"]] if entry.get("greek") else [])
                      + list(entry["wheels"])),
           "reflector": entry.get("reflector", "B"),
           "rings": entry["rings"],
           "positions": positions,
           "plugs": entry.get("plugs", ""),
           "ukw_pos": "A", "ukw_ring": "A"}
    assert len(cfg["positions"]) == n_wheels, "positions mismatch"
    return cfg


def historical_candidates(entries: list[dict], date: str) -> list[dict]:
    """Кандидаты режима Historical lookup: каждое сообщение дня с известным
    ключом -> расшифровка. Без scoring (скоринга пока нет)."""
    out = []
    for e in entries:
        if e["date"] != date or e["status"] != "verified":
            continue
        for m in e.get("messages", []):
            if not m.get("cipher") or not m.get("key"):
                continue
            cfg = None
            try:
                cfg = entry_machine_config(e, m["key"])
                plain = build_machine(cfg).decipher(m["cipher"])
            except Exception as ex:  # noqa: BLE001
                plain = f"<ошибка: {ex}>"
            out.append({"entry_id": e["id"], "date": e["date"], "message_id": m["id"],
                        "model": e["model"], "key": m["key"], "plaintext": plain,
                        "config": cfg})
    return out


# --- Benchmark (ядро) ---
class CancelledError(RuntimeError):
    """Кооперативная отмена длительной операции (benchmark/cracker)."""


def core_benchmark(chars: int = 20000, should_cancel=None) -> dict:
    """Замер EnigmaCore: chars/sec M3/M4, конструкция, positions-sweep.

    should_cancel: опциональный callable() -> bool для кооперативной
    отмены из worker-потока. При отмене бросает CancelledError.
    """
    res: dict = {}
    txt = "A" * chars
    cfg = {"model": "M3", "rotors": ["II", "IV", "V"], "reflector": "B",
           "rings": "BUL", "positions": "BUO", "plugs": "AV BS CG DL FU HZ IN KM OW RX"}
    t0 = time.perf_counter()
    build_machine(cfg)
    res["construct_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    t0 = time.perf_counter()
    build_machine(cfg).decipher(txt)
    dt = time.perf_counter() - t0
    res["m3_chars_sec"] = int(chars / dt)
    if should_cancel is not None and should_cancel():
        raise CancelledError("core benchmark cancelled")
    cfg4 = {"model": "M4", "rotors": ["Beta", "II", "IV", "I"], "reflector": "Thin-B",
            "rings": "AAAV", "positions": "VJNA", "plugs": "AT BL DF GJ HM NW OP QY RZ VX"}
    t0 = time.perf_counter()
    build_machine(cfg4).decipher(txt)
    res["m4_chars_sec"] = int(chars / (time.perf_counter() - t0))
    # positions-sweep: сколько стартовых позиций в секунду (короткий текст)
    probe, n = "AUFBEFEHL", 0
    t0 = time.perf_counter()
    for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if should_cancel is not None and n % 26 == 0 and should_cancel():
                raise CancelledError("core benchmark cancelled")
            c = dict(cfg)
            c["positions"] = a + b + "O"
            build_machine(c).decipher(probe)
            n += 1
    dt = time.perf_counter() - t0
    res["positions_per_sec"] = int(n / dt)
    res["positions_tested"] = n
    return res


def ocr_benchmark() -> dict:
    """Замер OCR: детерминированная синтетика -> pipeline.benchmark()."""
    try:
        from ocr.pipeline import OCRService
    except ImportError as ex:
        raise RuntimeError(f"OCR недоступен: {ex}") from ex
    from PIL import Image, ImageDraw, ImageFont
    lines = ["NCZW VUSX PNYM INHZ", "XMQX SFWX WLKJ AHSH",
             "VONV ONJL OOKS JHFF"]
    img = Image.new("RGB", (1200, 420), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("cour.ttf", 84)
    except OSError:
        font = ImageFont.load_default(size=84)
    for i, t in enumerate(lines):
        d.text((90, 50 + i * 150), t, font=font, fill="black")
    import numpy as np
    return OCRService().benchmark(np.array(img))
