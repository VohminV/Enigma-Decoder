#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release-gate тесты v1.0.0: упаковка, метаданные, experimental-статус G/K/D,
алиасы, настройки, отсутствие опасных API.

Запуск: pytest tests/test_release_gate.py (без workaround-флагов:
отключение hydra-плагина уже в pyproject addopts).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def _toml():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


# --- версия/лицензия/доки ---

def test_version_is_1_0_0():
    assert _toml()["project"]["version"] == "1.0.0"


def test_changelog_mentions_1_0_0():
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    assert "## [1.0.0]" in text


def test_license_exists_and_mit():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        text = f.read()
    assert "MIT License" in text
    assert _toml()["project"]["license"] == {"text": "MIT"}


def test_release_docs_present():
    for name in ("README.md", "SECURITY.md", "CHANGELOG.md",
                 "RELEASE_NOTES.md", "ARCHITECTURE.md",
                 "docs/RELEASE_GATE.md"):
        assert os.path.exists(os.path.join(ROOT, name)), name


def test_readme_disclaimers():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        text = f.read()
    assert "исторический" in text.lower()
    assert "не используйте" in text.lower() or "не предназначен" in text.lower()
    assert "experimental" in text.lower()


def test_manifest_lists_keys():
    with open(os.path.join(ROOT, "MANIFEST.in"), encoding="utf-8") as f:
        text = f.read()
    assert "keys.json" in text


def test_entry_points_declared():
    scripts = _toml()["project"]["scripts"]
    assert scripts["enigma-decoder"] == "main:main"
    assert scripts["enigma"] == "enigma:main"
    assert scripts["enigma-keydb"] == "keydb:main"


def test_entry_point_targets_importable():
    import enigma
    import keydb
    import main
    assert callable(main.main)
    assert callable(enigma.main)
    assert callable(keydb.main)


def test_pytest_addopts_disables_only_hydra():
    opts = _toml()["tool"]["pytest"]["ini_options"]["addopts"]
    assert opts == ["-p", "no:hydra_pytest"]
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" not in " ".join(opts)


# --- data files ---

def test_keys_json_loads_and_valid():
    import keydb
    entries = keydb.load_db()
    assert isinstance(entries, list) and len(entries) >= 1
    assert keydb.validate_db(entries) == {}


def test_db_resolve_env_override(tmp_path, monkeypatch):
    import keydb
    p = tmp_path / "k.json"
    p.write_text('{"entries": []}', encoding="utf-8")
    monkeypatch.setenv("ENIGMA_KEYS_PATH", str(p))
    assert keydb.resolve_db_path(None) == str(p)
    assert keydb.load_db() == []


def test_scoring_test_model_present():
    import scoring
    assert os.path.exists(scoring.TEST_MODEL_PATH)
    model = scoring.TetragramScorer.load(scoring.TEST_MODEL_PATH)
    assert model.table_size > 100


# --- experimental G/K/D ---

def test_experimental_metadata():
    import services
    for model in ("G", "G312", "G260", "K", "D"):
        assert services.MACHINE_MODELS[model]["experimental"] is True
    for model in ("I", "M3", "M4"):
        assert services.MACHINE_MODELS[model]["experimental"] is False


def test_gkd_construction_warns():
    from enigma import EnigmaCommercial, EnigmaG
    with pytest.warns(UserWarning, match="experimental"):
        EnigmaG("G312", ("I", "II", "III"), "AAAA", "AAAA")
    with pytest.warns(UserWarning, match="experimental"):
        EnigmaCommercial("K", ("I", "II", "III"), "AAA", "AAA")


def test_mline_construction_no_warning():
    import warnings

    from enigma import EnigmaMachine
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        EnigmaMachine(("I", "II", "III"), "B", "AAA", "AAA", model="M3")


# --- алиасы R-05 ---

def test_ambiguous_aliases_deprecated_but_work():
    from enigma import normalize_rotor
    with pytest.warns(DeprecationWarning, match="двусмыслен"):
        assert normalize_rotor("B") == "BETA"
    with pytest.warns(DeprecationWarning, match="двусмыслен"):
        assert normalize_rotor("G") == "GAMMA"


def test_canonical_names_no_warning():
    import warnings

    from enigma import normalize_rotor
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert normalize_rotor("Beta") == "BETA"
        assert normalize_rotor("I") == "I"


# --- настройки R-06 ---

def test_loglevel_mapping():
    import logging

    from main import loglevel_to_level
    assert loglevel_to_level("Debug") == logging.DEBUG
    assert loglevel_to_level("Normal") == logging.INFO
    assert loglevel_to_level("???") == logging.INFO


def test_settings_pages_wire_loglevel_dbpath_threads():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from gui.pages.keys_page import KeysPage
    from gui.pages.settings_page import SettingsPage
    _app = QApplication.instance() or QApplication([])  # держать ссылку
    s = SettingsPage()
    assert s.loglevel.count() == 2  # Normal/Debug подключён
    assert "резерв" in s.threads.toolTip().lower() or "reserve" in s.threads.toolTip().lower() \
        or "1.0.0" in s.threads.toolTip()
    k = KeysPage()
    assert hasattr(k, "_load")


# --- безопасность: опасные API отсутствуют ---

def test_no_dangerous_apis_in_production():
    import pathlib
    roots = [os.path.join(ROOT, name) for name in
             ("enigma.py", "services.py", "keydb.py", "main.py",
              "fast_enigma.py", "scoring.py")]
    roots += [str(p) for p in pathlib.Path(os.path.join(ROOT, "gui")).rglob("*.py")]
    roots += [str(p) for p in pathlib.Path(os.path.join(ROOT, "ocr")).rglob("*.py")]
    banned = ("pickle.loads", "yaml.unsafe_load", "os.system",
              "shell=True", "eval(", "exec(")
    hits = []
    for path in roots:
        text = open(path, encoding="utf-8").read()
        for token in banned:
            # Qt .exec() и format_exc — не то; проверяем точные совпадения
            if token in ("eval(", "exec("):
                import re
                if re.search(r"(?<![\w.])" + re.escape(token), text):
                    hits.append(f"{path}: {token}")
            elif token in text:
                hits.append(f"{path}: {token}")
    assert hits == [], hits


# --- round-trip всех моделей (ядро релиза) ---

def test_roundtrip_all_models_gate():
    import services
    from enigma import ALL_MODELS
    for model in ALL_MODELS:
        cfg = services.default_config(model)
        probe = "HELLOXWORLD"
        cipher = services.build_machine(cfg).encipher(probe)
        with __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            assert services.build_machine(cfg).decipher(cipher) == probe, model
