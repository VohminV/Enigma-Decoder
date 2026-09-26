# Changelog — Enigma Decoder

Формат: [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
версионирование: [SemVer](https://semver.org/lang/ru/).

## [1.0.0] — 2026-09-26

### Added
- Криптографический дисклеймер (README, SECURITY.md, GUI-подсказки):
  Enigma — только исторический/образовательный шифр.
- `SECURITY.md`: responsible disclosure, правила логов/секретов, лимиты.
- `ARCHITECTURE.md`: компоненты, data-flow, trust boundaries.
- `RELEASE_NOTES.md`, `CHANGELOG.md`, `LICENSE` (MIT).
- CI `.github/workflows/ci.yml`: lint (ruff), тесты, сборка, `pip audit`.
- Тесты `tests/test_release_hardening.py` (19 тестов): дубли роторов,
  `press`/`set_positions` валидация, лимиты текста/файлов/БД/sweep,
  санитизация plugboard-диалога, workers без QWidget-parent,
  отсутствие key-material в логах.
- Тесты `tests/test_release_gate.py` (21 тест): версия/лицензия/доки,
  entry points, data files, experimental-статус G/K/D, deprecation алиасов,
  wiring настроек, отсутствие опасных API, round-trip всех моделей.
- `docs/RELEASE_GATE.md`: воспроизводимые ворота релиза
  (139 passed без флагов, ruff clean, build+twine passed, wheel-smoke).
- DoS-лимиты: `enigma.MAX_TEXT_CHARS` (1M), `enigma.MAX_FILE_BYTES` (5МБ),
  `keydb.MAX_DB_BYTES` (10МБ), OCR 50МП/30МБ, PDF DPI 72..400,
  `positions_sweep(max_results=100_000)`.
- Ротация логов `enigma_gui.log` (1МБ × 3).

### Changed
- Версия `0.1.0` → `1.0.0` (`pyproject.toml`).
- `EnigmaMachine`: запрет повторяющихся подвижных роторов M-line.
- `press()` (I/M3/M4, G, K/D): строго одна буква A-Z, иначе `ValueError`.
- `FastEnigma.set_positions()`: проверка символов A-Z.
- `services.entry_machine_config()`: `assert` → `ValueError`.
- `legacy.load_machine()`: понятные `ValueError` вместо `KeyError`.
- `PlugboardDialog`: санитизация начальных пар с предупреждением.
- `CrackWorker`/`OCRWorker`: `parent=None` (стабильное владение QThread).
- `MachinePage._step`: видимое предупреждение вместо тишины.
- `search_experiments._test_vocab`: путь от файла модуля + понятная ошибка.
- `tools/build_scorer.py`: создание каталога вывода.
- GUI-логи: без значений ключей/колец/штекеров (только типы ошибок);
  `BenchmarkPage` не показывает внутренние детали в диалоге.

### Fixed
- Silent wrong-config: дубли M-line, мусор в `press()`/`set_positions()`.
- Потенциальный OOM: огромные тексты/файлы/БД/картинки/PDF/sweep.
- Key-material в `enigma_gui.log` через тексты исключений.
- CWD-зависимость тестового корпуса search-экспериментов.
- `QThread(parent=QWidget)` для Crack/OCR workers.

### Security
- Нет RCE/инъекций: `pickle/eval/exec/subprocess/shell` отсутствуют.
- Секретов в коде/истории не найдено (исторические ключи — публичные данные).
- Добавлены лимиты и санитизация (см. Added/Changed).
- G/K/D engagement: без изменений математики; добавлен честный статус
  «внутренние таблицы, внешнего эталона нет» (не маскируется под verified).

### Deprecated
- Ничего.

### Removed
- Ничего (обратная совместимость сохранена, кроме отклонения ранее
  молча принимавшихся невалидных конфигов — задокументировано здесь).

## [0.1.0] — историческая версия до релизного hardening
- Ядро I/M3/M4/G/K/D, GUI, база ключей, OCR, scorer/fast/search эксперименты,
  differential-тесты M-line против `py-enigma 1.0.2`, `docs/AUDIT.md` (фазы 7–9).
