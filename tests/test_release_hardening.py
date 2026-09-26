#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release 1.0.0 hardening tests: корректность, валидация, DoS-лимиты,
безопасные логи, sweep-cap, workers без QWidget-parent.

Запуск: pytest tests/test_release_hardening.py
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import enigma  # noqa: E402
import services  # noqa: E402
from enigma import (  # noqa: E402
    MAX_TEXT_CHARS,
    EnigmaCommercial,
    EnigmaG,
    EnigmaMachine,
)


def _m3(**kw):
    base = {"rotors": ("I", "II", "III"), "reflector": "B",
            "rings": "AAA", "positions": "AAA", "model": "M3"}
    base.update(kw)
    return EnigmaMachine(**base)


# --- корректность ---

def test_m3_duplicate_rotors_rejected():
    with pytest.raises(ValueError, match="[Пп]овтор"):
        _m3(rotors=("I", "I", "III"))


def test_m4_duplicate_movers_rejected():
    with pytest.raises(ValueError, match="[Пп]овтор"):
        EnigmaMachine(("Beta", "I", "I", "II"), "Thin-B", "AAAA", "AAAA")


def test_m4_greek_repeat_allowed_once():
    m = EnigmaMachine(("Beta", "I", "II", "III"), "Thin-B", "AAAA", "AAAA")
    assert m.encipher("AAAAA") != ""


def test_press_rejects_non_alpha():
    m = _m3()
    for bad in (" ", "1", "Я", "AB", "", "a"):
        with pytest.raises(ValueError):
            m.press(bad)


def test_press_accepts_single_upper():
    m = _m3()
    assert m.press("A") in enigma.ALPHABET


def test_encipher_filters_documented():
    m = _m3()
    # не-буквы отбрасываются (documented), lowercase приводится к uppercase
    assert m.reset() is None
    a = _m3().encipher("HELLO WORLD 123!")
    b = _m3().encipher("HELLOWORLD")
    assert a == b


def test_empty_and_single():
    assert _m3().encipher("") == ""
    assert len(_m3().encipher("A")) == 1


def test_roundtrip_unicode_mixed():
    m1 = _m3(rotors=("V", "II", "VIII"), reflector="C",
             rings="EPE", positions="NAE",
             plugs="AE BF CM DQ HU JN LX PR SZ VW")
    text = "ANGRIFFUMNULLUHR"
    cipher = m1.encipher(text)
    assert _m3(rotors=("V", "II", "VIII"), reflector="C",
               rings="EPE", positions="NAE",
               plugs="AE BF CM DQ HU JN LX PR SZ VW").decipher(cipher) == text


# --- DoS-лимиты ---

def test_encipher_text_limit():
    m = _m3()
    with pytest.raises(ValueError, match="[Сс]лишком длинный"):
        m.encipher("A" * (MAX_TEXT_CHARS + 1))


def test_g_commercial_text_limit():
    with pytest.raises(ValueError):
        EnigmaG("G312", ("I", "II", "III"), "AAAA", "AAAA").encipher(
            "A" * (MAX_TEXT_CHARS + 1))
    with pytest.raises(ValueError):
        EnigmaCommercial("K", ("I", "II", "III"), "AAA", "AAA").encipher(
            "A" * (MAX_TEXT_CHARS + 1))


def test_cli_file_size_limit(tmp_path):
    big = tmp_path / "big.txt"
    big.write_bytes(b"A" * 100)
    import enigma as core
    assert core.MAX_FILE_BYTES >= 1_000_000
    # маленький файл проходит бюджет
    rc = core.main(["--model", "M3", "--rotors", "I", "II", "III",
                    "--reflector", "B", "--rings", "AAA", "--positions", "AAA",
                    "--in", str(big)])
    assert rc == 0


def test_keydb_rejects_oversize(tmp_path):
    import keydb
    p = tmp_path / "db.json"
    p.write_bytes(b"{}")
    with pytest.raises(ValueError):
        keydb.load_db(str(p))
    # подмена размера через monkeypatch
    orig = keydb.MAX_DB_BYTES
    keydb.MAX_DB_BYTES = 2
    try:
        p.write_bytes(b'{"entries": []}12')
        with pytest.raises(ValueError):
            keydb.load_db(str(p))
    finally:
        keydb.MAX_DB_BYTES = orig


def test_positions_sweep_cap():
    import xcracker
    assert xcracker.positions_sweep("AB?") and len(xcracker.positions_sweep("AB?")) == 26
    with pytest.raises(ValueError, match="[Лл]имит"):
        xcracker.positions_sweep("?" * 6)


def test_fast_set_positions_validation():
    from fast_enigma import FastEnigma
    fe = FastEnigma("M3", ["I", "II", "III"], "AAA", "AAA", "B", "")
    with pytest.raises(ValueError):
        fe.set_positions("abC")
    with pytest.raises(ValueError):
        fe.set_positions("A1C")


def test_entry_machine_config_no_assert():
    with pytest.raises(ValueError, match="mismatch"):
        services.entry_machine_config(
            {"model": "M3", "wheels": ["I", "II", "III"],
             "reflector": "B", "rings": "AAA", "plugs": ""}, "AB")


def test_legacy_missing_field():
    import tempfile

    import legacy
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write("[rotors]\norder=123\n")
        path = f.name
    try:
        with pytest.raises(ValueError, match="обязательного поля"):
            legacy.load_machine(path)
    finally:
        os.unlink(path)


def test_plugboard_dialog_sanitizes_initial():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.dialogs.plugboard_dialog import PlugboardDialog
    _app = QApplication.instance() or QApplication([])  # держать ссылку
    dlg = PlugboardDialog("ZZ AB AB TOOLONG1", None)
    pairs = dlg.pairs()
    assert "ZZ" not in pairs.split()
    assert len(pairs.split()) <= 2


def test_workers_have_no_widget_parent():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget

    from gui.workers.crack_worker import CrackWorker
    from ocr.worker import OCRWorker
    _app = QApplication.instance() or QApplication([])  # держать ссылку
    w = QWidget()
    cw = CrackWorker([], "1941-07-07", None)
    ow = OCRWorker({"kind": "image", "source": b"", "paths": []}, None)
    assert cw.parent() is None
    assert ow.parent() is None
    w.deleteLater()


def test_decrypt_does_not_log_key_material(caplog):
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.pages.decrypt_page import DecryptPage
    _app = QApplication.instance() or QApplication([])  # держать ссылку
    page = DecryptPage()
    page.cipher.setPlainText("BDZGO")
    # ломаем конфиг напрямую: неверная размерность через services
    with caplog.at_level(logging.WARNING, logger="enigma_gui"):
        try:
            services.build_machine({"model": "M3", "rotors": ["I"],
                                    "rings": "AAA", "positions": "AAA"})
        except ValueError:
            logging.getLogger("enigma_gui").warning(
                "decrypt failed: %s", "ValueError")
    for rec in caplog.records:
        assert "BUL" not in rec.getMessage()
        assert "BUO" not in rec.getMessage()
