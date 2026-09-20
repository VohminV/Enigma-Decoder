#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Общий загрузчик reference-пакета py-enigma (не затеняя enigma.py проекта).

Использование: from _ref_loader import load_reference  (в тестах).
"""
import importlib.util
import os
import sysconfig

import pytest


def load_reference():
    for key in ("purelib", "platlib"):
        init = os.path.join(sysconfig.get_path(key), "enigma", "__init__.py")
        if os.path.exists(init):
            pkg_dir = os.path.dirname(init)
            spec = importlib.util.spec_from_file_location(
                "ref_enigma", init, submodule_search_locations=[pkg_dir])
            mod = importlib.util.module_from_spec(spec)
            import sys
            sys.modules["ref_enigma"] = mod
            spec.loader.exec_module(mod)
            return mod
    pytest.skip("reference py-enigma not installed (pip install -e '.[dev]')")
