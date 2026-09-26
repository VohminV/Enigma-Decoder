#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обязательный тест AUD-002/AUD-003: все 8 моделей строятся из defaults,
размерности корректны, CLI-defaults из MachineSpec.

Запуск: pytest test_specs.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import services  # noqa: E402
from enigma import ALL_MODELS, parse_args, spec_for, validate_dimensions  # noqa: E402

# Ожидаемые размерности из MachineSpec: model -> (wheels, rings, positions)
EXPECTED_DIMS = {
    "I": (3, 3, 3),
    "M3": (3, 3, 3),
    "M4": (4, 4, 4),
    "G": (3, 4, 4),
    "G312": (3, 4, 4),
    "G260": (3, 4, 4),
    "K": (3, 3, 3),
    "D": (3, 3, 3),
}


def test_all_models_known():
    assert set(ALL_MODELS) == set(EXPECTED_DIMS)


@pytest.mark.parametrize("model", ALL_MODELS)
def test_spec_dimensions(model):
    spec = spec_for(model)
    assert (spec.wheels, spec.rings, spec.positions) == EXPECTED_DIMS[model]
    assert len(spec.default_wheels) == spec.wheels
    if spec.distinct_wheels:
        assert len(set(spec.default_wheels)) == spec.wheels


def test_all_machine_models_build_defaults():
    """Главный тест: default-конфиг каждой модели валиден и строит машину."""
    for model in ALL_MODELS:
        cfg = services.default_config(model)
        spec = spec_for(model)
        assert len(cfg["rotors"]) == spec.wheels, model
        assert len(cfg["rings"]) == spec.rings, model
        assert len(cfg["positions"]) == spec.positions, model
        if spec.distinct_wheels:
            assert len(set(cfg["rotors"])) == spec.wheels, model
        if spec.default_reflector is not None:
            assert cfg["reflector"] == spec.default_reflector, model
        machine = services.build_machine(cfg)  # не должен бросать
        # дымовой roundtrip на СВЕЖЕЙ машине с тем же конфигом (состояние
        # роторов avanzaет, поэтому decipher на той же машине — ошибка теста):
        # ловит грубые ошибки сборки (неверный ETW/число роторов).
        probe = "HELLOXWORLD"
        cipher = machine.encipher(probe)
        assert services.build_machine(cfg).decipher(cipher) == probe, model


@pytest.mark.parametrize("model", ALL_MODELS)
def test_cli_defaults_build(model):
    """CLI без явных --rings/--positions строит рабочую машину (AUD-003).

    Дефолтные --rotors CLI — 3 колеса; для M4 нужно передать 4 явно
    (это требование размерности, а не defaults колец/позиций).
    """
    argv = ["--model", model, "--text", "HELLO"]
    if model == "M4":
        # CLI требует явных --rotors (4 шт.) и тонкого рефлектора —
        # это выбор конфигурации, а не defaults колец/позиций.
        argv = ["--model", model, "--rotors", "Beta", "I", "II", "III",
                "--reflector", "Thin-B", "--text", "HELLO"]
    args = parse_args(argv)
    assert args.rings is None and args.positions is None
    from enigma import build_machine
    machine = build_machine(args)  # не должен бросать
    cipher = machine.encipher("HELLO")
    assert build_machine(args).decipher(cipher) == "HELLO"


@pytest.mark.parametrize("model", ALL_MODELS)
def test_gui_widget_config_builds(model):
    """Конфиг MachineWidget по умолчанию строит машину (AUD-002)."""
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.widgets.machine_widget import MachineWidget
    app = QApplication.instance() or QApplication([])
    w = MachineWidget()
    idx = list(services.MACHINE_MODELS).index(model)
    w.model_box.setCurrentIndex(idx)
    app.processEvents()
    cfg = w.get_config()
    spec = spec_for(model)
    assert len(cfg["rings"]) == spec.rings, model
    assert len(cfg["positions"]) == spec.positions, model
    machine = services.build_machine(cfg)  # не должен бросать
    cipher = machine.encipher("TESTX")
    assert services.build_machine(cfg).decipher(cipher) == "TESTX", model


def test_validate_dimensions_error_format():
    """Формат ошибки Expected/Received из требования AUD-006."""
    with pytest.raises(ValueError, match="Expected"):
        validate_dimensions("G312", ("I", "II", "III"), "AAA", "AAA")
    with pytest.raises(ValueError):
        validate_dimensions("M3", ("I", "II"), "AAA", "AAA")
    # корректные размерности не бросают
    validate_dimensions("G312", ("I", "II", "III"), "AAAA", "AAAA")
    validate_dimensions("M4", ("Beta", "I", "II", "III"), "AAAA", "AAAA")
