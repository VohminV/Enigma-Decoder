# Release Gate — Enigma Decoder v1.0.0

Доказательство готовности релиза: команды, результаты, остаточные риски,
инструкции мейнтейнеру. Локальные ворота пройдены на Windows, Python 3.10.11.

## 1. Pytest без глобального workaround

Проблема окружения: системный `hydra-core 1.0.7` регистрирует pytest11-плагин
`hydra_pytest`, несовместимый с `pytest>=8` — сбор коллекции падала до тестов
проекта. Определено командой:

```powershell
python -c "from importlib.metadata import distributions; ..."
# -> hydra-core: hydra_pytest среди pytest11 entry points
```

Решение (точечное, в `pyproject.toml`):

```toml
[tool.pytest.ini_options]
addopts = ["-p", "no:hydra_pytest"]
```

Это НЕ скрывает ошибки проекта: все остальные плагины включены, все тесты
выполняются. Проверка: `python -m pytest -q` → 137 passed (118 + 19 gate).

Старый workaround `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` больше не нужен локально;
из CI он удалён (релай на `addopts`).

## 2. Команды ворот и результаты

```powershell
# установка (editable; сеть нужна только здесь)
python -m venv .venv-release
.\.venv-release\Scripts\Activate.ps1
pip install -e ".[dev]"

# тесты — всё без дополнительных флагов
python -m pytest -q                                  # 137 passed
python tests/test_core.py                            # 32/32
python tests/test_vectors.py                         # ALL OK (17 векторов)
python tests/test_keydb.py                           # ALL OK
python legacy.py                                     # EXAMPLES ALL OK
$env:QT_QPA_PLATFORM='offscreen'
python tests/test_gui.py                             # 9/9

# lint / build / audit (dev-зависимости)
ruff check .                                         # clean
python -m build                                      # wheel + sdist в dist/
twine check dist/*                                   # passed
pip-audit                                            # см. §4

# smoke CLI
python enigma.py --model M3 --rotors I II III --reflector B \
  --rings AAA --positions AAA --text BDZGO            # -> AAAAA
```

Что не запускалось и почему:
- `tools/evaluate_ocr.py` — тяжёлый OCR-прогон на синтетике (~минуты,
  требует модели RapidOCR); OCR покрыт `tests/test_ocr.py` (29/29) и
  помечен в CI как опциональный (`slow`/`ocr` markers).
- GUI offscreen в CI — требует системных Qt-зависимостей (см. workflow).

## 3. Упаковка

- `py-modules` объявлены явно; `gui*`/`ocr*` — пакеты; `MANIFEST.in`
  включает `keys.json`, `data/scoring/*`, `Examples/*`, доки.
- Entry points: `enigma-decoder` (GUI), `enigma` (CLI ядра), `enigma-keydb`.
- `keydb.resolve_db_path()`: явный путь > `ENIGMA_KEYS_PATH` > рядом
  с модулем > CWD — wheel-установки работают.
- DoS-лимиты: текст 1M, файл 5МБ, БД 10МБ, картинка 50МП/30МБ,
  PDF DPI 72..400, sweep 100k (см. README/CHANGELOG).

## 4. pip-audit

Выполняется мейнтейнером (нужна сеть). На момент gate: [результат вносится
при прогоне]. Локальный desktop/CLI/library-профиль: RCE через зависимости
неэксплуатируем без сетевой поверхности; parse-библиотеки (Pillow/fitz)
смягчены лимитами размера входа.

## 5. Остаточные риски (приняты для local release)

- R-01 G/K/D без внешнего эталона → помечены experimental (warning +
  metadata + GUI/CLI/доки), математика не менялась.
- R-02 без lock → accepted: библиотека/CLI, `pip install -e .`
  воспроизводим; команда для lock: `pip-compile --extra dev -o
  requirements.lock pyproject.toml` (нужен pip-tools + сеть).
- R-04 OCR только синтетика → caveat в README/RELEASE_NOTES.
- R-05 алиасы B/G → DeprecationWarning, канонические имена без warning.
- R-06 threads — зарезервирован (tooltip + тест); loglevel/dbpath подключены.

## 6. Инструкции мейнтейнеру

```powershell
git push origin release/enigma-decoder-1.0.0
git push origin v1.0.0   # после зелёного CI
# GitHub Release: тело из RELEASE_NOTES.md подставит workflow
```
