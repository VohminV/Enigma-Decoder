#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests AUD-006: validate_entry/validate_db отклоняют битые записи
с понятными Expected/Received-ошибками и принимают keys.json.

Запуск: pytest test_validation.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import keydb  # noqa: E402


def _base():
    return {
        "id": "t-1", "date": "1941-07-07", "model": "M3",
        "service": "Heer", "network": "x", "wheels": ["II", "IV", "V"],
        "greek": None, "reflector": "B", "rings": "BUL", "rings_alt": [],
        "plugs": "AV BS CG DL FU HZ IN KM OW RX", "status": "verified",
        "notes": "", "sources": [],
        "messages": [{"id": "m1", "key": "RAS", "grundstellung": "BUO",
                      "indicator": "IHO", "verified": "indicator"}],
    }


def test_real_db_valid():
    bad = keydb.validate_db(keydb.load_db())
    assert bad == {}, bad


def test_missing_field():
    e = _base()
    del e["rings"]
    assert any("rings" in err for err in keydb.validate_entry(e))


def test_bad_date():
    e = _base()
    e["date"] = "07-07-1941"
    assert any("YYYY-MM-DD" in err for err in keydb.validate_entry(e))
    e["date"] = "1941-02-30"
    assert any("calendar" in err for err in keydb.validate_entry(e))


def test_m3_vs_m4():
    # M4-запись с 3-буквенными кольцами и без greek — reject
    e = _base()
    e.update({"id": "t-m4", "model": "M4", "reflector": "Thin-B",
              "greek": None, "rings": "BUL"})
    errs = keydb.validate_entry(e)
    assert any("greek" in err for err in errs), errs
    assert any("4 letters" in err for err in errs), errs  # rings 3 vs 4
    # M3 с greek — reject
    e = _base()
    e["greek"] = "Beta"
    assert any("greek" in err for err in keydb.validate_entry(e))
    # M3 с тонким рефлектором — reject
    e = _base()
    e["reflector"] = "Thin-B"
    assert any("reflector" in err for err in keydb.validate_entry(e))


def test_g_dimensions():
    e = _base()
    e.update({"id": "t-g", "model": "G312", "wheels": ["I", "II", "III"],
              "reflector": "", "rings": "AAA", "plugs": "",
              "messages": [{"id": "m1", "key": "ABCD", "grundstellung": "AAAA",
                            "indicator": "XYZ", "verified": "indicator"}]})
    errs = keydb.validate_entry(e)
    assert any("Expected" in err and "4" in err for err in errs), errs
    e["rings"] = "AAAA"
    assert keydb.validate_entry(e) == [], keydb.validate_entry(e)


def test_rotor_rules():
    e = _base()
    e["wheels"] = ["I", "IX", "III"]
    assert any("IX" in err for err in keydb.validate_entry(e))
    e = _base()
    e["wheels"] = ["VI", "II", "III"]
    e["model"] = "I"
    assert any("not allowed" in err for err in keydb.validate_entry(e))
    e = _base()
    e.update({"model": "K", "wheels": ["I", "I", "III"], "reflector": "",
              "plugs": ""})
    assert any("distinct" in err for err in keydb.validate_entry(e))


def test_plugs_and_messages():
    e = _base()
    e["plugs"] = "AA"
    assert any("plugboard" in err for err in keydb.validate_entry(e))
    e = _base()
    e["messages"][0]["verified"] = "full"
    assert any("cipher" in err for err in keydb.validate_entry(e))
    e = _base()
    e["messages"] = [{"id": "m1"}, {"id": "m1"}]
    assert any("duplicate message" in err for err in keydb.validate_entry(e))


def test_validate_db_duplicates():
    bad = keydb.validate_db([_base(), copy.deepcopy(_base())])
    assert "t-1" in bad and any("duplicate entry" in err for err in bad["t-1"])


def test_uncertain_transcription_marker():
    # '?' в grundstellung/indicator — маркер ненадёжной транскрипции
    # (реальный случай spruch-24a); в key запрещён.
    e = _base()
    e["messages"] = [{"id": "m1", "key": "RAS", "grundstellung": "VIN?",
                      "indicator": "ZOV?", "verified": "full",
                      "cipher": "AA", "plain": "BB"}]
    assert keydb.validate_entry(e) == [], keydb.validate_entry(e)
    e["messages"][0]["key"] = "RA?"
    assert any("key" in err for err in keydb.validate_entry(e))
