# Release Gate — Enigma Decoder v1.0.0

Доказательство готовности релиза: команды, результаты, остаточные риски,
инструкции мейнтейнеру. Локальные ворота пройдены на Windows, Python 3.10.11,
ветка `release/enigma-decoder-1.0.0`.

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
выполняются. Проверка: `python -m pytest -q` → 139 passed.

Старый workaround `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` больше не нужен локально;
из CI он удалён (релай на `addopts`).

## 2. Команды ворот и результаты (факт прогона 2026-09-26)

```powershell
# инструменты — изолированный venv (системный Python не тронут)
python -m venv C:\Windows\Temp\opencode\venv-gate --system-site-packages
venv-gate\Scripts\python -m pip install ruff build twine pip-audit

# тесты — всё без дополнительных флагов
python -m pytest -q                                  # 139 passed, 27 warnings
                                                     # (warnings: ожидаемые experimental/Deprecation)
python tests/test_core.py                            # 32/32
python tests/test_vectors.py                         # ALL OK (17 векторов)
python tests/test_keydb.py                           # ALL OK
python legacy.py                                     # EXAMPLES ALL OK
$env:QT_QPA_PLATFORM='offscreen'
python tests/test_gui.py                             # 9/9

# lint / build / audit
ruff check .                                         # All checks passed (было 61,
                                                     # 47 автофикс + 10 вручную)
python -m build                                      # wheel 94 КБ + sdist 129 КБ
twine check dist/*                                   # PASSED оба
pip-audit (в wheel-venv)                             # 8 finding-ов, все —
                                                     # setuptools 65.5.0 аудит-venv
                                                     # (не runtime-зависимость;
                                                     # см. §4)

# smoke CLI (системный Python)
python enigma.py --model M3 --rotors I II III --reflector B \
  --rings AAA --positions AAA --text BDZGO            # -> AAAAA
# smoke установленного wheel (чистый venv-wheel + ENIGMA_KEYS_PATH)
pip install dist\enigma_decoder-1.0.0-py3-none-any.whl  # все runtime-deps с PyPI OK
import enigma,services,keydb,contracts,scoring,fast_enigma  # OK
import gui.main_window, ocr.pipeline                 # OK (offscreen)
enigma --text BDZGO ...                              # -> AAAAA
enigma-keydb list                                    # 5 записей
```

Что не запускалось и почему:
- `tools/evaluate_ocr.py` — тяжёлый OCR-прогон на синтетике (~минуты,
  требует модели RapidOCR); OCR покрыт `tests/test_ocr.py` (29/29) и
  помечен markers `slow`/`ocr` (`pyproject.toml`).
- GUI offscreen в CI — требует системных Qt-зависимостей (установлены
  в workflow: libegl1, libopengl0, libxkbcommon0, libdbus-1-3,
  libfontconfig1).

## 3. Упаковка

- `py-modules` объявлены явно; `gui*`/`ocr*` — пакеты; `MANIFEST.in`
  включает `keys.json`, `data/scoring/*`, `Examples/*`, доки.
- Entry points: `enigma-decoder` (GUI), `enigma` (CLI ядра), `enigma-keydb`.
- Wheel: весь код + LICENSE; `keys.json` — только в sdist (setuptools-wheel
  не включает корневые data-файлы). `keydb.resolve_db_path()`: явный путь >
  `ENIGMA_KEYS_PATH` > рядом с модулем > CWD — проверено в wheel-venv.
- DoS-лимиты: текст 1M, файл 5МБ, БД 10МБ, картинка 50МП/30МБ,
  PDF DPI 72..400, sweep 100k (см. README/CHANGELOG).

## 4. pip-audit

Факт: 8 findings, все — `setuptools 65.5.0` (PYSEC-2022-43012, PYSEC-2025-49,
PYSEC-2026-1918, PYSEC-2026-3447) в аудите-окружении (ensurepip venv),
не runtime-зависимость проекта (наш build-requirement: `setuptools>=68`;
runtime: PySide6/numpy/Pillow/opencv/rapidocr/pymupdf — чисто, findings нет;
`enigma-decoder` не на PyPI — ожидаемый skip). Неэксплуатируемо через
приложение (локальный desktop/CLI, без сети). Действие: нет; пересмотреть
при обновлении базового образа. CI job `audit` повторяет проверку при
каждом push.

## 5. Остаточные риски (приняты для local release)

- R-01 G/K/D без внешнего эталона → помечены experimental (warning +
  metadata + GUI/CLI/доки), математика не менялась.
- R-02 без lock → accepted: библиотека/CLI, `pip install -e .`
  воспроизводим; команда для lock: `pip-compile --extra dev -o
  requirements.lock pyproject.toml` (нужен pip-tools + сеть).
- R-04 OCR только синтетика → caveat в README/RELEASE_NOTES + markers.
- R-05 алиасы B/G → DeprecationWarning, канонические имена без warning.
- R-06 threads — зарезервирован (tooltip + тест); loglevel/dbpath подключены.
- CI actions version-pinned (не SHA): SHA-пининг — follow-up мейнтейнера:
  `gh api repos/<org>/<repo>/actions/...` или Dependabot; injection-рисков
  в workflow нет (нет untrusted input в shell, нет pull_request_target).

## 6. Инструкции мейнтейнеру

```powershell
git push origin release/enigma-decoder-1.0.0
git push origin v1.0.0   # после зелёного CI
# GitHub Release: тело из RELEASE_NOTES.md подставит workflow
```
