# Release Notes — Enigma Decoder v1.0.0

## Что нового
- Первый стабильный релиз исторического дешифратора
  Enigma I / M3 / M4 / G / G312 / G260 / K / D (GUI + CLI + библиотека).
- Строгая валидация Enigma-конфигов: дубли M-line запрещены,
  `press()` — только A-Z, понятные `ValueError` без stack trace в GUI.
- DoS-защита: лимиты текста (1M), файлов (5МБ), базы (10МБ),
  изображений (50МП/30МБ), PDF DPI 72..400, sweep-cap 100k.
- Безопасные логи: ротация 1МБ×3, без ключей/колец/штекеров/текстов.
- 19 новых hardening-тестов; всего pytest 118 passed + script-сюиты
  (core 32/32, vectors ALL OK, keydb ALL OK, legacy ALL OK, GUI 9/9).
- Документация: криптографический дисклеймер, `SECURITY.md`,
  `ARCHITECTURE.md`, `CHANGELOG.md`; CI (ruff + тесты + сборка + audit).

## Как обновиться / установить
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest
python main.py
python enigma.py --model M3 --rotors I II III --reflector B --rings AAA --positions AAA --text BDZGO
```

## Breaking changes
- Конфиги, ранее молча принимавшиеся, теперь отклоняются с `ValueError`:
  повторяющиеся подвижные роторы M-line (`I I I`, `Beta I I II`);
  `press()`/`FastEnigma.set_positions()` с не A-Z символами;
  входы длиннее лимитов. Это намеренное исправление silent-misconfig.

## Известные ограничения
- G/G312/G260/K/D — **experimental / internal-verified** (roundtrip +
  таблицы `Examples/Notches`; внешнего побайтового эталона не найдено;
  ядро выдаёт `UserWarning`). M-line (I/M3/M4) — validated векторами
  и differential-тестами против `py-enigma 1.0.2`.
- Полный автокрек (CrackerEngine) — `Not implemented` (кнопка отключена);
  доступен historical lookup + indicator solver + экспериментальные
  scorer/fast/search-модули.
- OCR — только латинская модель; готика/рукопись — низкая уверенность.
- Приложение локальное; не выставлять в сеть без отдельной изоляции.

## Артефакты
- Source: ветка `release/enigma-decoder-1.0.0`, tag `v1.0.0` (создаёт мейнтейнер).
- Python wheel/sdist: `python -m build` (см. «Exact Release Commands» в отчёте).
- Документация: `README.md`, `SECURITY.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `docs/AUDIT.md`.

## Проверки перед публикацией
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest` → 118 passed
  (в окружении со сломанным сторонним pytest-плагином hydra/omegaconf).
- `python tests/test_core.py`, `tests/test_vectors.py`, `tests/test_keydb.py`,
  `legacy.py`, `tests/test_gui.py` (offscreen) → ALL OK.
