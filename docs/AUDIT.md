# Enigma Decoder Technical Audit

Дата: 2026-09-20. Метод: чтение всего кода, запуск всех тестов, измерение benchmark, воспроизведение дефектов. Без refactor — только inspect → test → measure → document → prioritize.

Повторный прогон 2026-09-20 после очистки дерева от регенерируемых артефактов (`__pycache__/`, `*.pyc`, `enigma_gui.log` — удалены, исходники не тронуты): все 6 сюит PASS с чистого состояния, все 3 CRITICAL-дефекта воспроизводятся. Замеры повторного прогона: M3 ~351k chars/s, M4 ~296k chars/s, sweep ~13.7k pos/s, construct 0.08 ms (разброс в пределах шума vs первый прогон).

## Executive Summary

Проект — локальное Python-приложение (PySide6 GUI + собственный Enigma Core на I/M3/M4/G/K/D + JSON-база ключей + RapidOCR pipeline). Честная документация: отсутствующий CrackerEngine/scorer/fast-path явно помечены `Not implemented`, кнопки отключены.

Ядро M-line проверено сильными историческими векторами (M3 `AAAAA→BDZGO`, Enigma I 1930 полный текст, M4 U-264, M4 Dönitz P1030681 + индикатор, Wetter M3==M4, DoubleStep/Notches таблицы) — всё проходит. Формулы Ringstellung, stepping до шифрования, double-step — корректны по результатам тестов.

Найдено **3 критических дефекта** (ломают заявленные функции: Core Benchmark, все модели G/K/D в GUI, CLI-defaults для G), **6 high**, **~10 medium**. Криптоанализа, скоринга и fast-движка нет вообще — это Missing, а не Broken. Исторические проводки M-line подтверждены векторами; engagement-множества G/K и формула D — предположения проекта без независимой перекрёстной проверки.

Статус: криптографическое ядро M-line — Correct; G/K/D в GUI — Broken; Benchmark ядра — Broken; Cracker — Missing; Scorer — Missing; FastEnigma — Missing; OCR — работает, но только на синтетике.

## Current Architecture

```text
Project architecture

GUI (gui/, PySide6)          — 7 страниц, виджеты, диалоги, workers
 ↓ imports only
Services (services.py)       — сборка конфигов, historical lookup, benchmark
 ↓ imports only
Core (enigma.py)             — EnigmaMachine / EnigmaG / EnigmaCommercial, Rotor, Reflector
Data (keys.json + keydb.py)  — JSON-база суточных ключей, verify/decrypt CLI
OCR (ocr/)                   — pipeline → preprocessing → engine(RapidOCR) → postprocessing
```

Entry points: `main.py` (GUI), `enigma.py` (CLI ядра), `keydb.py` (CLI базы), `legacy.py` (проверка Examples-файлов симулятора 1.x), `test_*.py`, `tools/evaluate_ocr.py`.

| Component | File | Responsibility | Dependencies | Public API | Problems |
|---|---|---|---|---|---|
| GUI shell | `gui/main_window.py` | sidebar, страницы, статусбар, шорткаты, межстраничные колбэки | pages | `goto/page/apply_config_to_decrypt/decrypt_with_config/ocr_to_decrypt/ocr_to_crack` | closeEvent останавливает только Crack-worker (AUD-011) |
| Decrypt | `gui/pages/decrypt_page.py` | ручной шифр/дешифр через services | `services` | `on_run` | молча отбрасывает не-A-Z (AUD-012) |
| Crack | `gui/pages/crack_page.py` + `gui/workers/crack_worker.py` | индикатор-солвер + исторический поиск в QThread | `services` | `start/stop/set_custom_cipher` | Full-режим честно отключён; worker parented к QWidget (AUD-010) |
| OCR page | `gui/pages/ocr_page.py` + `ocr/worker.py` | preview/ROI, запуск OCR в QThread, batch, PDF | `ocr.*` | `on_run/on_stop` | worker leak при закрытии (AUD-011) |
| Keys | `gui/pages/keys_page.py` | поиск/импорт/экспорт/редактор `keys.json` | `services` | `search` | нет валидации схемы, неатомарная запись, перезапись импортированного файла (AUD-006/007) |
| Machine | `gui/pages/machine_page.py` | диагностика роторов, пошаговый тест | `services` | `on_run` | `_step` глотает исключения молча (AUD-024) |
| Benchmark | `gui/pages/benchmark_page.py` | замер ядра/OCR | `services` | `on_run` | Core Benchmark сломан (AUD-001); замеры в GUI-потоке (AUD-005) |
| MachineWidget | `gui/widgets/machine_widget.py` | конфиг машины для Decrypt/Machine/Crack | `services.MACHINE_MODELS` | `get_config/set_config` | 3 буквы rings/positions для G (надо 4), дубли I,I,I (AUD-002) |
| Services | `services.py` | тонкий слой GUI→ядро | `enigma`, `keydb`, `ocr.pipeline` | `build_machine/process_text/default_config/indicator_solve/db_entries/search_entries/entry_machine_config/historical_candidates/ocr_benchmark` | `core_benchmark` не определён (AUD-001); `default_config` невалиден для G/K/D (AUD-002) |
| Core | `enigma.py` | I/M3/M4/G/K/D + CLI | stdlib | `EnigmaMachine/EnigmaG/EnigmaCommercial/Rotor/Reflector/parse_plugs/build_machine` | CLI-defaults для G (AUD-003); алиасы B/G (AUD-019) |
| Data | `keydb.py` + `keys.json` | 5 записей, verify/decrypt | `enigma` | `load_db/find/build_machine/verify_message/verify_entry` | JSON без схемы/индексов/миграций (by design, AUD-006) |
| OCR | `ocr/pipeline.py,preprocessing.py,engine.py,postprocessing.py,models.py,worker.py` | image/PDF→pre→RapidOCR→normalize; RAW/NORMALIZED раздельно | rapidocr, cv2, numpy, PIL, fitz | `OCRService.run/run_pdf/batch/benchmark` | alternatives всегда пусты (AUD-013); чувствительность к вёрстке (AUD-018) |

Зависимости направлены правильно: GUI→services→core, циклов нет (проверено импортом). Бизнес-логики в QWidget почти нет (валидация — в core/services). База — JSON через services, не SQLite (поэтому «thread-safety SQLite» неприменимо; `load_db` читает файл каждый раз — потокобезопасно для чтения).

## Enigma Core

Проверено чтением кода + прогоном векторов (все PASS 2026-09-20):

- Stepping **до** обработки символа (`press`: `_step()` первая строка) — Correct.
- Double-step: `_step_service_trio` проверяет `middle.at_notch()` → step middle+left; затем `right.at_notch()` → step middle; затем right.step. Порядок верный; тест `ADQ→AER→BFS` и DoubleStep-таблица (`ADO…BFU`, 6 нажатий) PASS.
- Ringstellung: `offset = pos - ring; (wiring[(c+offset)%26]-offset)%26` — стандартная корректная формула; тест `M3 AAAAA→BDZGO` PASS (классический вектор), rings matter / positions matter PASS.
- Порядок роторов: `rotors` слева направо; forward — `reversed(self.rotors)` (справа налево), backward — слева направо. Correct.
- M4: греческий ротор статичен — `_step` берёт `rotors[1:]`; тест 500 символов PASS. Совместимость Beta+Thin-B==B / Gamma+Thin-C==C: статическая композиция + полный Wetter M3==M4 PASS.
- Reflector involution для всех 5 — PASS. Plugboard до+после, взаимность, лимит 10, запрет AA/дублей — PASS. `never self-encrypts` — PASS. `reset` восстанавливает позиции — PASS. `encipher` пропускает не-A-Z (документировано как свойство, но GUI об этом молчит — AUD-012).
- G carry-шаг (без double-step, UKW шагает через цепочку) — таблица NZAM→ODGW incl. Lobster PASS; roundtrip всех 3 вариантов PASS.
- K/D рычажный шаг; K engagement Y/E/N; D окно = Y+ring (сдвиг с кольцом доказан тестом `d_a/d_b`); roundtrip K/D PASS; `K AAAAA→JTOUN` PASS.
- Notches M4 NZAM 10 нажатий PASS.

NOT VERIFIED без внешнего reference-движка: побайтовое сравнение с независимой библиотекой (в репо её нет; ближайшее — Examples-файлы симулятора через `legacy.py`, все 5 проверок PASS).

## Historical Data

Классификация утверждений:

| Утверждение | Статус | Основание |
|---|---|---|
| M-line wiring I–VIII, Beta/Gamma | Verified historical fact (в рамках проекта) | Векторы U-264, Dönitz, I-1930, BDZGO PASS |
| UKW A/B/C, Thin-B/Thin-C | Verified (в рамках проекта) | Те же векторы + Wetter M3==M4 |
| Notch I–V (Q,E,V,J,Z), VI–VIII (ZM) | Verified (в рамках проекта) | Double-step/Notches таблицы PASS |
| M4 процедура (греч. статичен, 4-букв. кольца/позиции) | Verified (в рамках проекта) | U-264 + Dönitz PASS |
| Индикаторная процедура Kriegsmarine (Grundstellung→key→тело) | Verified (в рамках проекта) | `QEOB@NAEM→CDSZ`, Dönitz `ASTV` PASS |
| G wiring G/G312/G260 + engagement-множества (17/15/11) | Project assumption, corroborated | Только roundtrip + step-таблица из Examples; внешнего источника в репо нет |
| K engagement Y/E/N (notch−8) | Project assumption | Только roundtrip; вывод из cryptomuseum описан в комментарии test_core |
| D engagement = Y+ring (notch на корпусе) | Project assumption | Только roundtrip + unit на сдвиг |
| K/G default wiring = коммерческая | Project assumption | `K wheels == G default` — внутренняя консистентность, не внешний факт |
| Ключи keys.json (Heer 1941, Potsdam/U-534) | Verified / Published | `test_keydb.py` ALL OK; записи 1945-05-02 — published без шифротекста (честно) |
| Поправки к источникам (WUQ vs WUO, TH-транспозиция, AD vs AV) | Project assumption, documented | Зафиксированы в `cipher_notes/notes` — проверяемо движком |

Источников-файлов в репо нет (только URL в keys.json). Не исправлять wiring догадками — при расхождении с внешним источником писать как есть.

## Cracker

Факт: CrackerEngine отсутствует. Есть: (1) индикатор-солвер (расшифровка индикатора на Grundstellung — мгновенно, реален); (2) исторический lookup по дате в QThread с кооперативной отменой, прогрессом, покандидатными сигналами. Скоринга нет — кандидаты инспектируются вручную (честно написано в UI). Режим «Historical + automatic» выполняет только historical часть.

| what exists | what works | placeholder | missing |
|---|---|---|---|
| indicator solver | да (GUI-тест не покрывает, но `test_keydb` покрывает ту же математику) | — | — |
| historical lookup worker | да (GUI-тест: 1 кандидат по 1941-07-07) | — | — |
| Full automatic search | — | отключенная кнопка + тултип | CrackerEngine, генерация кандидатов, pruning, ranking, verification |
| scoring | — | подпись «No scoring available» | scorer полностью |
| parallelization | — | спинбокс threads «резерв под Phase 7+» | worker-пул |
| cancellation | да (кооперативная, Start→Stop→Start возможен) | — | тест многократного Start/Stop (ручной сценарий не прогонялся) |

Search-space (вычислено, M3/M4 при 10 штекерах; plugs(10)=150 738 274 937 250 ≈ 1.5e14):

- M3: порядок 8P3=336 × UKW 2 × кольца 26³=17 576 × позиции 26³=17 576 × штекеры ≈ 1.5e14 → **≈3.1e25**.
- M4: greek 2 × 8P3=336 × thin 2 × кольца 26⁴=456 976 × позиции 26⁴ × штекеры → **≈4.2e28**.
- Перебираемо сегодня: только позиции 26³=17 576 (<2 c при 13 533 pos/s); кольца+позиции 26⁶≈3.1e8 ≈ 6.3 ч на одном ядре. Штекеры брутфорсом невозможны — нужен crib/Bombe-подход, а не перебор.
- Bottleneck-прежде-всего: измеренный Enigma ~3e5 chars/s даёт потолок; scoring отсутствует, поэтому Cir no bottleneck пока не существует. Векторные таблицы/плёночный precompute — после появления scorer и профилирования, не раньше. GPU не предлагать: CPU-бутлнек ещё не измерен на реальной crack-нагрузке (её нет).

## Scoring

Отсутствует полностью (Missing). Нечего аудитить, кроме интерфейса: `historical_candidates`/`CrackWorker` возвращают plain без score; добавление scorer — новое поле item + колонка таблицы, cracker трогать не нужно (архитектурно замена возможна). Требование «очень быстрый поиск + плохой scorer = мусор» сейчас неприменимо — поиска нет.

## OCR

Pipeline (проверен чтением + `test_ocr.py` 29/29 PASS + `test_gui.py` OCR-блок PASS):

```text
image → load_image_rgba(copy, исходник не мутирует) → preprocess(copy) →
RapidOCREngine(PP-OCRv6, ONNX CPU, offline, модели в site-packages) →
reading-order → raw → EnigmaTextNormalizer → normalized. RAW и NORMALIZED хранятся раздельно.
```

- Engine: RapidOCR 3.9.2, детектор PP-OCRv6_det_small + классификатор + recognizer PP-OCRv6_rec_small; CPU onnxruntime. Версии зафиксированы окружением, не репозиторием (нет lock — AUD-004).
- Preprocessing: deterministic (тест PASS), input untouched (PASS); профили Original/Document/Typewritten/Historical Scan/Photograph/High Contrast/Ciphertext; deskew только при |angle|>10° (движок терпит ~10° — замерено, задокументировано); low-res warning <300px; апскейл по высоте текста.
- Confidence: средний по блокам; блоки <0.6 подсвечены в raw; suspicious-список (pos,char,score). Порог 0.6 — константа в коде, калибровка не приложена.
- Опасные замены: Conservative — без замен (default, корректно); Balanced чинит 0→O 1→I 5→S 8→B **с логированием каждой** (позиция/исходник/замена); Aggressive +6→G 2→Z. Замены цифра→буква только в этом направлении (контекст A-Z) — приемлемо, т.к. логируются и политика явная. Обратных замен (O→0) нет — правильно.
- Потеря RAW невозможна по построению: `raw` и `normalized.text` раздельно в pipeline/worker/GUI (raw_edit и norm_edit — разные виджеты, оба редактируемы; renormalize локально из raw).
- Качество (измерено, синтетика 2026-09-20): `test_ocr.py` вёрстка (1200×420, шаг 150) — CER 0.0 во всех 5 кейсах (clean/lowres/rot8/tint/noisy15), conf 0.95–1.0. `tools/evaluate_ocr.py` вёрстка (1200×460, шаг 160): avgCER 0.054, avgWER 0.359, avgConf 0.97, но `text0-*` детерминированно CER 0.719 (`ZHNINXSMZNHSXMSXX…`) — чувствительность к вёрстке (AUD-018). Режимы General/Historical/Enigma разделены; отдельных замеров по Historical-документам нет. Evaluation dataset с реальными сканами отсутствует — accuracy на реальном мире UNKNOWN.
- Интеграция OCR→Cracker: передаётся только плоский текст (`Send to Crack` → custom_box). `OCRCharacter{character,confidence,alternatives}` существует как dataclass, но `alternatives` всегда `[]` (RapidOCR не отдаёт) и cracker их не потребляет — архитектурный gap зафиксирован в коде честно (AUD-013).

## GUI

PySide6 6.11.2. 7 страниц, MachineWidget общий, колбэки через MainWindow (не clipboard). Проверено `test_gui.py` 9/9 PASS (offscreen).

- Потоки: OCR и Crack — в QThread с прогрессом/отменой; Decrypt/Machine — синхронно, но операции <1 мс (construct 0.067 мс) — допустимо. Benchmark — синхронно секунды (AUD-005, HIGH).
- Состояние: конфиг живёт в виджетах; межстраничная передача через колбэки MainWindow — приемлемо для масштаба.
- Ошибки: ValueError → warning с текстом; неожиданные → critical «См. лог» + traceback в файл (правильно: технический traceback не главный UI-текст).
- Шорткаты Ctrl+Return/Ctrl+Enter/Escape — есть. DPI/resize: стандартные layout'ы, явного high-DPI кода нет (Qt6 масштабирует сам — OK). Длинные тексты/изображения: QTextEdit + preview-скейл; cap на размер изображения нет (AUD-023 LOW).
- G/K/D в GUI сломаны полностью (AUD-002 CRITICAL).

## Threading

- `CrackWorker(QThread)`: кооперативная отмена (`_cancel` + `isInterruptionRequested`), поток не убивается; finished/cancelled/error сбрасывают `_worker=None`; повторный Start возможен. GUI из worker не трогается (только сигналы). Гонок на `_results` нет (append только в слоте GUI-потока).
- `OCRWorker(QThread)`: то же; PDF/image/batch ветки с проверками отмены между страницами/файлами. Данные через dict (без numpy через сигналы — `_pack` округляет; боксы — списки).
- Проблемы: parent=QWidget для QThread (AUD-010); OCR-worker не останавливается при закрытии окна (AUD-011); сценарий Start→Stop→Start многократно — код допускает, но тест отсутствует (gap).
- QThreadPool/QRunnable не используются (и не нужны при текущей нагрузке).

## Database

SQLite нет — `keys.json` (5 записей) + `keydb.py`. Аудит по факту:

- Connection lifecycle / thread-safety / транзакции / индексы / миграции / corruption handling: NOT APPLICABLE (плоский JSON, чтение целиком за 0.2 мс).
- Чтение из GUI идёт через `services.db_entries()` каждый `search()` — потокобезопасно (только чтение), но без кэша.
- Import: только `isinstance(data, list)` (AUD-006). Export: прямая запись. Edit: неатомарная запись + перезапись импортированного пути (AUD-007).
- Сущности не смешаны: запись = суточный ключ дня (model/wheels/greek/reflector/rings/plugs/sources/status), сообщение = индикатор/grundstellung/message key/cipher/plain/verified-уровень. Разделение daily key / message key / procedure — корректно. `rings_alt` хранит альтернативные кольца из источников — честно.

## Performance

Измерено 2026-09-20 (Windows, Python 3.10, CPU):

```text
Benchmark
-----------------------------
Operation       Result
EnigmaCore M3   ~375 000 chars/sec (20k chars, ключ BUL/BUO + 10 plugs)
EnigmaCore M4   ~285 800 chars/sec (20k chars, Beta II IV I + 10 plugs)
Positions sweep ~13 500 pos/sec (676 позиций, проба 9 букв incl. construct)
Construct       ~0.07 ms (M3 build)
Scorer          N/A (Missing)
Cracker         N/A (Missing)
OCR             total ~2 880 ms (pre 12 ms, ocr 2 869 ms, post 0 ms; 1200×420, 48 симв., conf 0.993)
DB import       0.2 ms (5 записей, load целиком)
Startup         QApp 0.12 s + MainWindow 2.19 s (offscreen; 첫 OCR-импорты ленивые)
```

Top bottlenecks (фактические, не предполагаемые): (1) OCR inference ~2.9 c/кадр — на 2 порядка дольше всего остального; (2) Enigma Python ~3e5 chars/s — потолок будущего брутфорса позиций; (3) MainWindow 2.2 c — приемлемо, но причина не профилирована; (4–5) отсутствуют как класс: scorer/cracker ещё не написаны, оптимизировать нечего.

Память: изображения ×2 (original+processed) + preview-pixmap без cap (AUD-023); кандидаты cracker — единицы (streaming/top-N понадобится только с настоящим cracker); benchmark-история — строки таблицы (мелочь); лог без ротации.

## Security

Локальное приложение; проверено: `pickle/eval/exec/subprocess/shell` — отсутствуют (совпадения grep — `traceback.format_exc` и Qt `.exec()`). `json.load` для импорта (безопасно, но без валидации — AUD-006). `PIL.Image.open` для чужих файлов + `fitz.open` для PDF — стандартные риски декомпрессионных бомб/битых файлов: PIL по умолчанию только предупреждает; cap и try/except в `_open_image/_open_pdf` есть (GUI показывает ошибку, не падает). Path traversal: файлы только через QFileDialog + запись только выбранного пути; SQLite-инъекций нет (нет SQLite). CSV-исполнения нет (импорт только JSON, как данные).

## Dependencies

Манифеста нет: `requirements.txt`, `pyproject.toml`, lock — отсутствуют (AUD-004). Факт окружения: PySide6 6.11.2, rapidocr 3.9.2, pymupdf 1.28.2, Pillow 12.3.0, numpy 2.2.6, opencv-python 4.13.0.92, onnxruntime-directml 1.23.0, torch 2.13.0+cu126 (тяжёлый, зачем — неизвестно, в коде не импортируется), pytest 9.1.1. README ставит `PySide6 rapidocr pymupdf Pillow numpy` без пинов и **без opencv-python** (импортируется `ocr/preprocessing.py` — установка по README сломает OCR). Windows: `cour.ttf` предполагается (есть в Win; `test_ocr.py` упадёт без него — AUD-017). Неиспользуемые/дубли: torch/coqui/ultralytics в окружении — мусор окружения, не зависимости проекта (не декларированы нигде).

## Testing

5 скриптов, все PASS 2026-09-20: `test_core.py` 32/32, `test_vectors.py` 17/17, `test_keydb.py` ALL OK, `test_ocr.py` 29/29, `test_gui.py` 9/9, `legacy.py` ALL OK (5 групп). Coverage-инструмент не настроен. Есть: unit (core), векторы, keydb-инварианты, OCR normalizer/CER/WER/preprocess determinism/batch/PDF, GUI smoke offscreen.

Критически необходимые — статус: known vectors ✓, double stepping ✓, ring settings ✓ (через vectors + rings matter), plugboard ✓, reset ✓, reference comparison ✗ MISSING (нет внешней библиотеки), OCR normalization ✓, database import ✗ MISSING (импорт GUI не тестирован), cracker cancellation ✗ MISSING (ручной сценарий не автоматизирован).

## Packaging

`EnigmaDecoder.exe` сегодня несобираем без работы: нет PyInstaller-spec, нет манифеста зависимостей; риски: модели RapidOCR лежат в `site-packages/rapidocr/models` (нужны hooks/data), `keys.json` резолвится от `services.__file__` (в bundle нужен sys._MEIPASS или collect_data), `cour.ttf` — системный шрифт Win (в bundle/на других ОС пропадёт), QSettings-пути, `enigma_gui.log` рядом с exe (прав на запись может не быть), onnxruntime-directml DLL. Решение: не паковать до стабилизации архитектуры (G-конфиг, benchmark, зависимости) — как и сказано в задаче.

## Critical Problems

ID: AUD-001
Severity: CRITICAL
File: `services.py`
Location: строка 144 (`# --- Benchmark (ядро) ---def core_benchmark(...)`)
Problem: `core_benchmark` не определён — комментарий склеен с `def`, весьIndented-блок ниже — просто мёртвый код на уровне модуля (docstring-строка + операторы выполняются при импорте? нет: строка 145 — строковый литерал, дальше `res: dict = {}` и т.д. — ВНИМАНИЕ: строки 145+ выполняются на уровне модуля при импорте, включая `build_machine(cfg)` замеры? Проверить: после склейки `def` пропал, тело стало module-level кодом. Импорт services при этом успешен и быстр (0.015 c), значит код… — фактически модуль содержит висячие `res[…]`/`t0`/`txt` операции на верхнем уровне. Импорт работает, но выполняет мусорную работу и может бросать исключения в будущем. А `services.core_benchmark` отсутствует → `benchmark_page._run_core` всегда падает в `except Exception` с «Ошибка замера, см. лог»).
Why it matters: кнопка Core Benchmark мертва; плюс module-level мусор выполняется при каждом импорте.
Evidence: `dir(services)` без `core_benchmark`; `python -c "services.core_benchmark()"` → AttributeError; строка 144 дословно `# --- Benchmark (ядро) ---def core_benchmark(chars: int = 20000) -> dict:`.
Recommended fix: разбить строку на комментарий + `def core_benchmark(...)`, убедиться что тело внутри функции; добавить regression-тест `services.core_benchmark()` smoke.
Risk of fix: минимальный (одна строка + тест).

ID: AUD-002
Severity: CRITICAL
File: `gui/widgets/machine_widget.py` (`_rebuild`, `get_config`), `services.py` (`default_config`, `build_machine` для G)
Location: `machine_widget.py:84-120,138-150`; `services.py:72-82`
Problem: модели G/G312/G260/K/D невозможно использовать из GUI. Причины: (a) виджет строит 3 rotor/ring/pos-бокса, а `EnigmaG` требует 4-буквенные rings/positions `[UKW,L,M,R]`; (b) дефолтные колёса `I,I,I` — дубли, `EnigmaG/EnigmaCommercial` бросают «колёса не должны повторяться»; (c) UKW pos/ring виджет показан, но для G игнорируется (EnigmaG берёт UKW из rings[0]/positions[0]); (d) `services.default_config("G312"/"K"/...)` возвращает те же невалидные 3-буквенные конфиги.
Why it matters: 5 из 8 заявленных моделей мертвы во всех GUI-страницах (Decrypt/Machine/Crack-indicator).
Evidence: воспроизведено offscreen: `G312 → FAIL: Enigma G: колёса не должны повторяться`, `K → FAIL: Commercial: колёса не должны повторяться`; `default_config` для G/K/D → BUILD FAIL.
Recommended fix: для G — 4 ring/pos-бокса (первый = UKW) + дефолт без дублей (напр. I II III); для K/D — дефолт без дублей; `default_config` синхронизировать; regression-тест: `build_machine(widget.get_config())` для каждой модели.
Risk of fix: средний — меняется layout виджета; regression-тест обязателен.

ID: AUD-003
Severity: CRITICAL
File: `enigma.py`
Location: `parse_args` defaults (`--rings AAA`, `--positions AAA`) + `build_machine` G-ветка
Problem: CLI-дефолты не зависят от модели: `enigma.py --model G312 --rotors III II I --text HELLO` падает (`Кольца G [UKW,L,M,R] — 4 буквы`), т.к. дефолт 3-буквенный.
Why it matters: ломает заявленный в README пример для G без явных `--rings AAAA --positions XXXX`.
Evidence: прогон 2026-09-20: с `AAAA/NZAM` → `LGUEX` OK; без них → exit 2 с ошибкой колец.
Recommended fix: дефолты rings/positions по модели (G*: AAAA) или понятная ошибка с подсказкой; тест CLI-парсинга.
Risk of fix: низкий.

## High Priority Problems

ID: AUD-004
Severity: HIGH
File: (отсутствуют) `requirements.txt` / `pyproject.toml`; `README.md`
Location: repo root
Problem: нет манифеста зависимостей и пинов; README ставит `PySide6 rapidocr pymupdf Pillow numpy`, но код импортирует `cv2` (`ocr/preprocessing.py`) — установка по README даёт сломанный OCR. Тяжёлые транзитивные (torch в окружении) никак не задекларированы/ограничены.
Why it matters: невоспроизводимое окружение; «быстрый старт» из README неполон.
Evidence: `grep import cv2 → ocr/preprocessing.py`; файлов манифеста нет (Test-Path False ×4).
Recommended fix: `requirements.txt` с пинами + `opencv-python` внутри; README поправить; позже — lock.
Risk of fix: низкий.

ID: AUD-005
Severity: HIGH
File: `gui/pages/benchmark_page.py`
Location: `_run_core` (строки 88-111), `_run_ocr` (62-86)
Problem: замеры выполняются в GUI-потоке (лишь `processEvents`), блокируя интерфейс на секунды (OCR замерен 2.9 c; core при починке ~2–5 c по тултипу).
Why it matters: нарушает собственное правило «GUI thread никогда не выполняет benchmark»; зависание окна.
Evidence: чтение кода — нет worker; замер OCR 2881 ms wall.
Recommended fix: вынести в QThread (как OCRWorker/CrackWorker) с progress/disable-кнопок; regression — кнопки disabled во время замера + результат доставлен сигналом.
Risk of fix: средний (новый worker, но паттерн уже есть в кодовой базе).

ID: AUD-006
Severity: HIGH
File: `gui/pages/keys_page.py`
Location: `_import` (270-284)
Problem: валидация импорта — только `isinstance(data, list)`. Битые записи (нет `date/wheels/rings`, дубли `id`, неверный формат даты) роняют `search/_details/_use` с KeyError позже, в другом месте.
Why it matters: один чужой JSON ломает страницу ключей; источник — недоверенные данные (импорт исторических данных!).
Evidence: чтение кода; `_details` обращается к `e['service']`, `e['wheels']` напрямую.
Recommended fix: `validate_entry()` (обязательные поля, формат даты, длины rings/positions, построение машины как в EntryDialog, дубли id) до принятия файла; тест на битый JSON.
Risk of fix: низкий.

ID: AUD-007
Severity: HIGH
File: `gui/pages/keys_page.py`
Location: `_edit` (245-268), `_import`
Problem: (a) запись неатомарна (прямой `open(path,"w")`; `.bak`-копия не спасает от crash mid-write); (b) после Import `_db_path` указывает на чужой файл, и Edit перезаписывает его (сюрприз для пользователя).
Why it matters: потеря/порча базы ключей; молчаливая модификация внешнего файла.
Evidence: строки 257-264; `self._db_path = path` в `_import`.
Recommended fix: write-to-temp + os.replace; после импорта — либо «Save as», либо явный индикатор «редактируется внешний файл»; тест roundtrip.
Risk of fix: низкий.

ID: AUD-008
Severity: HIGH
File: `enigma.py` (G_ENGAGE, K_ENGAGE, D_ENGAGE_BASE), `test_core.py`, `test_vectors.py`
Location: строки 84-99 `enigma.py`
Problem: нет differential-тестов против независимой reference-реализации. Engagement-множества G (17/15/11), K (Y/E/N) и формула D (Y+ring) — деривации проекта; проверены только roundtrip + внутренние step-таблицы. Ошибка в этих константах даст «правильно выглядящий», но исторически неверный шифр.
Why it matters: самая опасная категория — silent wrong crypto для G/K/D.
Evidence: в репо нет сторонней Enigma-библиотеки; `legacy.py` сверяет только M-line/G-step через файлы симулятора.
Recommended fix: взять reference (напр. well-known Python-реализация с тестами, зафиксировать версию+источник) и прогнать differential vectors для G/K/D; зафиксировать источник каждой wiring-строки.
Risk of fix: низкий (только тесты, код не менять без причины).

ID: AUD-009
Severity: HIGH
File: `gui/pages/crack_page.py`
Location: режим `mode_both` (59, 242-247)
Problem: «Historical + automatic» выполняет только historical часть без scoring; пользователь может решить, что автоматический поиск отработал. Плюс scorer/cracker/fast отсутствуют как класс — Phase 7+ не начата даже с интерфейсов.
Why it matters: вводит в заблуждение; блокирует главное направление развития.
Evidence: чтение кода; честная подпись есть, но режим называется так, будто automatic произойдёт.
Recommended fix (план, не код сейчас): определить интерфейсы `Candidate{config,plaintext,score}`, `Scorer.score(text)->float`, `CrackerEngine.search(...)` со streaming/top-N + отменой; начать со scorer (n-gram) отдельно от cracker.
Risk of fix: средний — сначала контракты и benchmark scorer, затем движок.

## Medium Priority Problems

ID: AUD-010 — Severity: MEDIUM — `gui/workers/crack_worker.py:24-27`, `ocr/worker.py:24-27`: QThread с parent=QWidget. Работает, но владение QObject между потоками хрупко (удаление родителя + `_worker=None` без deleteLater). Fix: `parent=None` + `deleteLater` на finished; риск низкий.

ID: AUD-011 — Severity: MEDIUM — `gui/main_window.py:135-138` (`closeEvent`): останавливается только Crack-worker; OCR-worker продолжает после закрытия окна (до конца страниц), процесс может висеть. Fix: останавливать оба + `wait()`; риск низкий.

ID: AUD-012 — Severity: MEDIUM — `enigma.py:349-354` + `decrypt_page.py:87-105`: `encipher` молча пропускает не-A-Z; GUI не сообщает, что цифры/пробелы отброшены. Fix: счётчик пропущенных + hint в UI; риск низкий.

ID: AUD-013 — Severity: MEDIUM (архитектурный gap, не баг) — `ocr/models.py:73-82`: `OCRCharacter.alternatives` всегда `[]`; cracker принимает плоский текст. Будущий учёт альтернатив потребует `List[OCRCharacter]`-входа в scorer/cracker. Сейчас не реализовывать; зафиксировать контракт.

ID: AUD-014 — Severity: MEDIUM/LOW — `services.py:123-141`: `historical_candidates` собирает `entry_machine_config` дважды на сообщение; `CrackWorker` перерасшифровывает сообщения базы вместо использования проверенного plaintext (когда custom_cipher пуст). Fix: переиспользовать; риск низкий.

ID: AUD-015 — Severity: MEDIUM/LOW — `services.py:97-105` + `keys_page`: сравнение дат строками без валидации формата; битый ввод → пустой результат без ошибки. Fix: валидация `YYYY-MM-DD` + сообщение.

ID: AUD-016 — Severity: MEDIUM/LOW — `main.py:12-13`: лог INFO только в файл без ротации; уровней DEBUG нет в использовании; `enigma_gui.log` 0 байт. Fix: RotatingFileHandler + использование `loglevel` из Settings (сейчас спинбокс ни на что не влияет).

ID: AUD-017 — Severity: MEDIUM — `test_ocr.py:41`: `ImageFont.truetype("cour.ttf", 84)` на уровне модуля без fallback → на системе без шрифта весь файл падает OSError (а `services.ocr_benchmark` и `test_gui` fallback имеют). Fix: try/except как elsewhere; риск низкий.

ID: AUD-018 — Severity: MEDIUM — OCR generalization: синтетическая вёрстка evaluate (1200×460/шаг 160) даёт детерминированный CER 0.719 против 0.0 на вёрстке test_ocr; реальных сканов в evaluation нет. Fix: собрать eval-dataset (синтетика разных вёрсток + реальные фото), пороги CER по профилям; не «чинить» движок под одну картинку.

ID: AUD-021 — Severity: MEDIUM — репозиторий не под VCS (git нет), `__pycache__/` лежит в дереве, `.gitignore` нет. Fix: `git init` + игнор + первый коммит аудита.

## Low Priority Problems

ID: AUD-019 — LOW — `enigma.py:133-140`: алиасы `"B"→BETA`, `"G"→GAMMA` двусмысленны в CLI (буква B как имя ротора). GUI не предлагает, риск только для API/CLI. Fix: убрать однобуквенные алиасы греческих.

ID: AUD-020 — INFO — `enigma.py:183-187`: пример в сообщении об ошибке колец (`'A'*n`) тривиален. Косметика, не трогать без повода.

ID: AUD-022 — LOW (сейчас) — нет PyInstaller-spec/портируемого режима; `keys.json` от `__file__`, модели в site-packages, `cour.ttf` системный, лог рядом с exe. Не паковать до стабилизации (см. Packaging).

ID: AUD-023 — LOW — изображения без cap: original+processed+pixmap в RAM; PIL без явного `MAX_IMAGE_PIXELS`/лимита. Fix: лимит мегапикселей + даунскейл с предупреждением.

ID: AUD-024 — LOW — `machine_page.py:113-116`: `_step` глотает исключение только в лог, пользователь не узнает. Fix: QMessageBox как в `_build`.

## Recommended Architecture

Целевая схема (эволюция, не революция — services-слой уже существует и правилен):

```text
GUI (pages/widgets)
 ↓ только через services + сигналы; никакого enigma/keydb/ocr напрямую
Application Services (services.py + будущие scoring.py/cracker_engine.py contracts)
 ↓
Core (enigma.py: чистые вычисления, без I/O) · OCR (pipeline) · Data (keydb + validate_entry)
```

Конкретно, по одному изменению на причину:

1. Починить склейку AUD-001 (1 строка) — разблокирует Benchmark.
2. G-конфиг: 4-й UKW-бокс + дефолты без дублей (AUD-002/003) — разблокирует 5 моделей.
3. Вынести benchmark в worker (AUD-005) — убирает фриз.
4. `validate_entry()` + атомарная запись + Save-as семантика (AUD-006/007) — защищает данные.
5. Контракты `Scorer`/`CrackerEngine` + differential-тесты G/K/D против reference (AUD-008/009) — фундамент Phase 7.
6. Манифест зависимостей + git (AUD-004/021) — воспроизводимость.
7. Остальное — по приоритету, малыми PR с regression-тестами.

Без новых абстракций «ради SOLID»: каждый пункт выше привязан к воспроизведённому дефекту или блокирующему gap.

## Implementation Roadmap

Порядок (каждый шаг: зафиксировать → тест → исправить → прогнать → записать):

1. AUD-001: разбить строку 144 services.py; smoke-тест `core_benchmark()`; прогнать Benchmark из GUI. (30 мин)
2. AUD-002/003: G/K/D конфиг в виджете + `default_config` + CLI-дефолты; regression-тест build для всех 8 моделей. (0.5–1 день)
3. AUD-021/004: git init + .gitignore; `requirements.txt` с пинами (+opencv-python); README-правка. (0.5 дня)
4. AUD-006/007: `validate_entry`, атомарная запись, импорт/экспорт-тесты на битом JSON. (0.5–1 день)
5. AUD-005/011/010: benchmark-worker; остановка OCR-worker при закрытии; parent=None workers. (1 день)
6. AUD-008: выбрать reference-движок (версия+источник), differential vectors G/K/D. (1 день)
7. AUD-009/013: контракты `Scorer`/`CrackerEngine`/`OCRCharacter[]`-вход; n-gram scorer + benchmark scorer отдельно от cracker. (фаза 7, недели)
8. AUD-012/015/016/017/018/023/024: UX-мелочи, логирование, eval-dataset OCR. (фон)
9. Упаковка (AUD-022): только после 1–7.

## Open Questions

1. Какой внешний reference-движок считать эталоном для G/K/D (нужны версия + источник + лицензия)?
2. Источники wiring G312/G260 и engagement-множеств: какие документы считать каноническими (cryptomuseum wiring.htm? G-111 doc? Ch/Tz номера)?
3. D «notch на корпусе (Y+ring)» — есть ли первичный источник, или это реконструкция по поведению симулятора?
4. Кольца Potsdam `rings_alt` (AAEL/EPEL, AACU/VCCH): какое считать каноническим daily ring, какое — message-effective? Сейчас в базе оба, используется первое.
5. Целевая платформа упаковки — только Windows portable, или установщик + Linux?
6. Допустимый словарь/язык для будущего scorer (немецкий военный с X-сепараторами?) и откуда n-gram модель (размер, лицензия)?
7. Нужен ли SQLite вообще (рост базы до сотен записей?) или JSON с валидацией достаточен?

- Enigma M-line (I/M3/M4 stepping/wiring/plugs/reset): Correct (векторы PASS)
- Enigma G шаг/проводки: Needs verification (нет внешнего эталона)
- Commercial K/D engagement: Needs verification (только roundtrip)
- G/K/D в GUI и CLI-дефолты: Broken (AUD-002/003)
- Core Benchmark: Broken (AUD-001)
- Reference implementation в репо: Missing
- Historical Keys данные: Correct (verified) / Published-честно; схема без валидации импорта
- CrackerEngine / Scoring / FastEnigma: Missing (заявлено честно)
- OCR pipeline: Correct на синтетике; Real-world accuracy: Unknown (нет dataset)
- OCR→Cracker uncertainty: Missing (gap зафиксирован)
- GUI/Threading: Correct кроме Benchmark-блокировки и shutdown-утечки
- Database: N/A (JSON); robustness импорта: Broken-ish (HIGH)
- Dependencies/Packaging/VCS: Missing
- Производство: Blocked до AUD-001..003; затем High-приоритеты.

## Remediation

Выполнено 2026-09-20 strictly по приоритету задачи. Каждый пункт:
изменение → regression test → полный suite → следующий пункт.
Механика Enigma не менялась (только добавлены Spec/валидация/CLI-defaults).

AUD-001 FIXED
Problem: комментарий склеен с `def core_benchmark` (services.py:144) —
функции нет, кнопка Benchmark мертва, module-level мусор при импорте.
Fix: строка разбита на комментарий + настоящий `def`; добавлен опциональный
`should_cancel` для кооперативной отмены (нужен AUD-005); добавлен
`services.CancelledError`.
Files changed: `services.py`, `test_services_benchmark.py` (new), `conftest.py` (new).
Tests added: exists / import без side effects (<2 c) / shape результата /
отмена бросает CancelledError.
Verification: pytest 4/4; `services.core_benchmark(20000)` возвращает все 5 ключей.

AUD-002 FIXED
Problem: GUI строил 3 буквы rings/positions для G (надо 4) и дубли I,I,I.
Fix: единый источник истины `enigma.MachineSpec` (`MACHINE_SPECS`, 8 моделей:
wheels/rings/positions/defaults/reflectors/options/distinct/plugs/ukw_separate).
`services.MACHINE_MODELS` теперь derived (только ярлыки), `default_config()` —
из Spec, `MachineWidget._rebuild` — боксы из Spec (у G 4 бокса, первый = UKW;
отдельный UKW-блок только K/D), `EntryDialog._save_check` — размерности из Spec.
Никаких `if model == ...` по GUI: ветвление только по полям Spec.
Files changed: `enigma.py`, `services.py`, `gui/widgets/machine_widget.py`,
`gui/pages/keys_page.py`, `test_specs.py` (new).
Tests added: `test_all_machine_models_build_defaults` + dims/defaults/widget.
Verification: pytest test_specs 27/27; ручная проверка 8 моделей в GUI
(контролы + encrypt/decrypt roundtrip через DecryptPage) — ALL OK.

AUD-003 FIXED
Problem: CLI-дефолты rings/positions `AAA` ломали `--model G312`.
Fix: `--rings/--positions` default None → заполнение из MachineSpec в
`build_machine()`; явные значения уважаемы; неверная размерность даёт
Expected/Received-ошибку через `validate_dimensions()`.
Files changed: `enigma.py` (parse_args + build_machine), `test_specs.py`.
Tests added: `test_cli_defaults_build` x8 (M4 с явными rotors+Thin-B —
это выбор конфигурации, покрыт тестом).
Verification: все 8 моделей строятся из defaults; старые CLI-примеры README
проверены (M3/M4/G312/K).

requirements/pyproject FIXED
Problem: манифеста не было; README ставил без opencv-python (OCR падал).
Fix: `pyproject.toml` (runtime: PySide6, numpy, Pillow, opencv-python,
rapidocr, pymupdf + dev: pytest, py-enigma==1.0.2 как test-only reference);
README — venv + `pip install -e ".[dev]"` + note про OCR-модели в комплекте
rapidocr; проверки — `python -m pytest` + классические сюиты.
Files changed: `pyproject.toml` (new), `README.md`.
Verification: `tomli.load` OK; зависимости соответствуют реальным импортам.

Git PARTIAL
Problem: репозитория нет; игнорируемых правил нет.
Fix: `.gitignore` готов (`__pycache__`, `.pytest_cache`, `.venv`, IDE, `*.log`,
`*.bak`, benchmark/ocr-артефакты, `keys_local.json`; `keys.json` и `Examples/`
НЕ игнорируются). `git status` → `not a git repository`.
Status: OPEN (инициализация и коммит — отдельным решением, без необходимости
не делаем). Repository structure подготовлена.

AUD-006 FIXED
Problem: импорт keys.json проверял только `isinstance(list)`.
Fix: `keydb.validate_entry()` (required fields, types, date YYYY-MM-DD +
календарь, model, rotor names/allowed/distinct, greek только M4, reflector
по Spec — M3≠M4 ловится, rings/rings_alt длины, plugs через parse_plugs,
messages: дубли id, уровни, обязательные поля уровня, длины key/grundstellung;
`?` разрешён только в grundstellung/indicator как маркер ненадёжной
транскрипции — реальный случай spruch-24a) + `validate_db()` (дубли id).
Подключено к KeysPage._import (reject с первыми 5 ошибками) и к
EntryDialog._save_check. По пути validator поймал latent-баг сравнения
регистра рефлекторов (`Thin-C` vs `THIN-C`) — исправлен.
Files changed: `keydb.py`, `gui/pages/keys_page.py`, `test_validation.py` (new).
Tests added: 9 тестов (реальная БД валидна; missing/bad-date/M3vsM4/
G-dims/rotors/plugs+messages/duplicates/?-marker).
Verification: pytest 9/9 в файле; `test_keydb.py` ALL OK.

AUD-007 FIXED
Problem: неатомарная запись; Edit перезаписывал импортированный чужой файл.
Fix: `keydb.atomic_write_json()` (tmp в том же каталоге + flush/fsync +
`os.replace` — атомарно на Windows в пределах тома; чистка tmp при ошибке).
Ownership: `KeysPage._edit_target()` — импортированный внешний файл read-only,
правка идёт в локальную копию (user override) с явным сообщением; собственная
база — на месте. `_edit`/`_export` — через atomic_write_json (+ `.bak` сохранён).
Files changed: `keydb.py`, `gui/pages/keys_page.py`, `test_atomic.py` (new).
Tests added: roundtrip + отсутствие tmp-мусора + перезапись валидна +
_edit_target ownership (3 случая).
Verification: pytest 3/3 в файле.

AUD-005 FIXED
Problem: benchmark'и выполнялись в GUI-потоке (фриз секунды).
Fix: `gui/workers/benchmark_worker.py` (QThread, parent=None, kinds core/ocr,
сигналы started/stage/result/finished/cancelled/error, кооперативная отмена
через `should_cancel`); `BenchmarkPage` переведена на worker + кнопка Stop +
`on_stop` (Escape); Fast/Cracker кнопки по-прежнему честно disabled.
Benchmark cancellation: running → cancel_requested (флаг) → finished/cancelled/
error; принудительного убийства потока нет.
Files changed: `gui/workers/benchmark_worker.py` (new),
`gui/pages/benchmark_page.py`, `test_workers.py` (new).
Tests added: core-worker результат в GUI-потоке без блокировки + отмена до
старта даёт cancelled; close-тест (ниже).
Verification: pytest test_workers 2/2.

OCR worker shutdown FIXED
Problem: closeEvent останавливал только Crack; OCR-worker мог пережить окно.
Fix: `MainWindow.closeEvent` останавливает Crack+OCR+Benchmark (on_stop) +
bounded `wait(3000)` на каждый — закрытие не висит.
Files changed: `gui/main_window.py`, `test_workers.py`.
Tests added: `test_close_stops_workers_no_hang` (Crack+OCR запущены → close
<15 c, worker'ы завершены, исключений нет).
Verification: pytest PASS (2.97 c, close мгновенный).

AUD-008 PARTIAL
Problem: G/K/D — только roundtrip (может быть одинаково неправильным).
Fix: подключён независимый reference py-enigma 1.0.2 (Brian Neal, MIT, данные
Rijmenants; dev-only, production-код не импортирует; зафиксирован в pyproject).
`test_differential.py`: sanity BDZGO через reference; 3 исторических вектора
через оба движка; 40 случайных M3 + 40 случайных M4 конфигов (роторы I–VIII,
кольца/позиции/0–10 штекеров, тексты 5/50/300 — многократные обороты и
double-step зоны) в обе стороны; при failure — полный дамп
Machine/Rotors/Rings/Positions/Reflector/Plugboard/Input/Expected/Actual.
Результат: 80/80 конфигов побайтово совпали — M-line proven vs reference.
G/K/D: OPEN — публичных reference-реализаций не найдено; остаются внутренние
step-таблицы из файлов симулятора Enigma 1.x (legacy.py, независимый источник).
Побочно зафиксировано: топ-модуль `enigma.py` затеняет pip-пакет `enigma`
(reference грузится через importlib как ref_enigma) — учесть при упаковке.
Files changed: `test_differential.py` (new), `pyproject.toml` (dev extra).
Tests added: 4 теста (sanity + historic + 2×40 random).
Verification: pytest 4/4.

Misleading Historical+automatic FIXED
Problem: UI обещал «Historical + automatic» без automatic.
Fix: `mode_both` и `mode_full` disabled с тултипами Not implemented;
режим называется «Historical lookup»; подпись результата — всегда честная
(«Automatic search: Not implemented»).
Files changed: `gui/pages/crack_page.py`.
Tests added: покрыто существующим `test_gui.py` (crack worker results PASS).
Verification: `test_gui.py` 9/9.

Contracts (подготовка Phase 7, без реализации) DONE
`contracts.py` (new): `Candidate` (+`from_historical` адаптер), `Scorer` (ABC),
`CrackerEngine` (ABC, streaming/top-N, кооперативная отмена), `SearchProgress`.
Ноль эвристик/моделей (проверено тестом на отсутствие ngram/hillclimb).
Files changed: `contracts.py` (new), `test_contracts.py` (new, 3 теста).
Verification: pytest 3/3. Реализация движка НЕ начата (по задаче).

## Итоговые счётчики тестов

pytest: 99 passed, 0 failed (из каталога `tests/`: test_specs 27 +
test_services_benchmark 4 + test_validation 9 + test_atomic 3 +
test_workers 2 + test_differential 4 + test_contracts 3 +
test_scoring 10 + test_xcrack 8 + test_fast_differential 7 +
test_fast_bench 5 + test_search 17;
script-style сюиты запускаются как `python tests/<file>`).
- tests/test_core.py: 32/32
- tests/test_vectors.py: 17/17
- tests/test_keydb.py: ALL OK
- tests/test_ocr.py: 29/29
- tests/test_gui.py: 9/9
- legacy.py: ALL OK

Примечание: после remediation все `test_*.py` и `conftest.py` переехали
в каталог `tests/` (script-style сюиты: `python tests/<file>`, pytest: bare
`python -m pytest` из корня). Упоминания старых путей выше — историческая
запись аудита; актуальные пути — здесь.

```text
REMEDIATION STATUS

CRITICAL:
0 remaining (AUD-001, AUD-002, AUD-003 FIXED)

HIGH:
1 remaining (Git: OPEN — инициализация/коммит отдельным решением;
AUD-004-covered-by-pyproject FIXED; AUD-005 FIXED; AUD-006 FIXED;
AUD-007 FIXED; AUD-008 PARTIAL — M-line proven, G/K/D differential OPEN;
misleading-mode FIXED)

Tests:
pytest 52 passed, 0 failed
core 32/32, vectors 17/17, OCR 29/29, GUI 9/9, keydb ALL OK, legacy ALL OK

Differential:
M3 40/40 + M4 40/40 random configs own == py-enigma 1.0.2 (both directions);
historic U-264 / Dönitz / BDZGO через оба движка совпали.
G/K/D: no public reference found — OPEN.

Benchmark (повторный прогон после remediation):
M3 ~351k chars/s, M4 ~296k chars/s, sweep ~13.7k pos/s, construct 0.08 ms,
OCR ~2.9 s/кадр (pre ~12 ms, ocr ~2.87 s), DB 0.2 ms, старт окна ~2.2 c.

Remaining known issues (не маскируем):
- Git: репозиторий не инициализирован (структура готова: .gitignore).
- G/K/D differential vs external reference: OPEN (нет публичного эталона).
- pytest в этом окружении требует PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
  (сломанный сторонний pytest11-плагин hydra/omegaconf в системном
  окружении — не относится к проекту).
- Топ-модуль enigma.py затеняет PyPI-пакет enigma (учтено в тестах через
  importlib; при упаковке/переименовании — решить отдельно).
- CrackerEngine/Scorer/FastEnigma: только контракты, реализации нет (по плану).
```

Ручная проверка GUI 8 моделей (offscreen, DecryptPage): M3/M4/I (3/3/3 бокса,
рефлектор вкл, штекеры вкл), G/G312/G260 (3 ротора + 4/4 бокса [UKW,L,M,R],
рефлектор выкл, штекеры выкл), K/D (3/3 + UKW-блок, рефлектор выкл) —
encrypt/decrypt roundtrip через реальную страницу для всех 8: ALL OK.
Остановка по задаче: CrackerEngine НЕ реализован, показан итог remediation.

## Phase 7

Статус: Scorer implemented (experimental baseline), ExperimentalCracker
implemented (small controlled search), production cracker NOT implemented.
Механика Enigma не менялась. GUI не менялся (disabled automatic mode сохранён).
OCR не менялся. G/K/D differential остаётся OPEN.

Архитектура Scorer (`scoring.py`, соответствует `contracts.Scorer` без
изменения ABC: `name` + `score(text)->float`):
- `normalize_for_scoring`: A-Z uppercase без пробелов, своя (не OCR).
  `"HELLO WORLD!" -> "HELLOWORLD"`, вход не мутирует.
- `NGramScorer(order 1..4, log_probs, floor)`: score = средний log10 prob
  на n-грамму (length-invariant ranking), невиданные — floor, детерминирован.
- `TetragramScorer` — baseline. Save/load JSON (`to_dict/from_dict/save/load`).
- Offline, без GUI, без зависимости от модели Enigma.

Training data (`data/scoring/` + `tools/build_scorer.py`):
- `test_corpus.txt` — маленький deterministic корпус ТОЛЬКО для unit tests
  (~70 слов военной лексики). Не production-модель (зафиксировано здесь и в
  `data/scoring/README.md`).
- `test_tetragrams.json` — собранная модель (478 тетраграмм, floor −4.702),
  воспроизводимо: `python tools/build_scorer.py --corpus
  data/scoring/test_corpus.txt --order 4 --out data/scoring/test_tetragrams.json`.
- Production corpus: TODO (OPEN) — источник, лицензия, разделимость — см.
  `data/scoring/README.md`. Ничего не скачивается автоматически.

Candidate: контракт `contracts.Candidate` достаточен без изменений
(config/plaintext/score/key/note) — проверено использованием в поиске.

Experimental search (`xcracker.py`, реализует `contracts.CrackerEngine.search`
без изменения ABC: constraints/scorer — параметры конструктора):
- `ExperimentalCracker(config_template, positions_list, scorer, top_n)`:
  фиксированная конфигурация + явный список позиций + Scorer → top-N.
- `positions_sweep("AB?"/"???")` — контролируемая генерация объёма.
- `TopCandidates(limit)`: bounded heap, score desc + tie-break key asc,
  весь результат не хранится.
- Отмена: кооперативная через `should_cancel` → `services.CancelledError`
  (принудительного убийства потока нет). Стриминг: `on_candidate` при входе
  в top-N, `on_progress` каждые 64 + финал.
- Без multiprocessing/GPU/эвристик (запрет этапа соблюдён).

Benchmark (замерено 2026-09-20, раздельно — core ≠ scorer ≠ combined):
- scorer: ~3 268 000 chars/sec (tetragram, 390-char текст) — scorer НЕ bottleneck.
- combined decrypt+score: ~222 000 chars/sec, ~5 700 positions/sec
  (676 позиций × 39-char cipher, M3 + 10 plugs).
- core отдельно: M3 ~351k chars/sec (см. Remediation).
- Вывод: bottleneck pipeline — симуляция Enigma, не скоринг. Оптимизация core
  НЕ ускорит скоринг и наоборот — подтверждено раздельным замером.

Tests (18 новых, все PASS):
- scoring (10): normalization, ABC, determinism, empty/short→floor,
  natural>random на домене тестового корпуса (не universal claim),
  save/load, пересборка корпуса→та же таблица, порядки 1–3, throughput.
- xcrack (8): sweep размеры/порядок, top-N bound/order/tie-break,
  synthetic crack (ниже), отмена (CancelledError, быстро, частичный объём
  не досчитывается), стриминг (эмиссии + финальный progress 676/676),
  пустые входы, benchmark-замер.
- Synthetic cracking test: known plaintext
  `ANGRIFFUMNULLUHRVONBERLINXWETTERBERICHT` (M3 II IV V/B/BUL/10 plugs) →
  sweep `??O` (676 позиций) → истинный ключ `BUO` rank 1/676 в top-20
  (margin −3.90 vs −4.59 у ближайшего). Рангу 1 не требуемя контрактом —
  assert на membership в top-N.

Regression: pytest 70/70 + core 32/32 + vectors 17/17 + keydb ALL OK +
legacy ALL OK + OCR 29/29 + GUI 9/9 + CLI BDZGO→AAAAA. GUI startup и Crack UI
не тронуты (test_gui PASS без изменений).

Known limitations (не production-ready, честно):
- Тестовая модель слабая (478 тетраграмм, gap natural/random ~0.7) —
  достаточна для experimental sweep сотен позиций, не для полного keyspace.
- Full brute force M3 ~3e25 / M4 ~4e28 — не пытаемся (ограничение этапа).
- G/K/D differential = OPEN (без изменений; scorer это не маскирует).
- TODO G/K/D: независимые публичные reference vectors, wiring, спецификации,
  differential tests (статус из аудита сохранён).
- Production corpus: OPEN (см. data/scoring/README.md).

Критерий готовности Phase 7:
existing tests PASS (70 + все сюиты) + scorer tests PASS (10) +
synthetic crack PASS (rank 1/676) + benchmark recorded (выше) +
cancellation PASS + streaming PASS + GUI regression PASS (9/9 без изменений) +
G/K/D status OPEN. Выполнен полностью.

STOP: full brute force / annealing / hill climbing / crib solver /
multiprocessing / GPU / neural scorer — НЕ начаты, ждут отдельного этапа
проектирования настоящего CrackerEngine.

## Phase 8

Статус: FastEnigma implemented (experimental evaluator), reference core
не тронут, production cracker NOT implemented. GUI/OCR/KeyDB/MachineSpec
не менялись. Scorer не менялся. G/K/D differential остаётся OPEN.

Аудит hot path (замерено до оптимизации, M3 + 10 plugs):
- construction: median ~43 мкс (676 конструкций в sweep ≈ 29 мс, т.е. ~60%
  короткого sweep уходило на перестройку объектов, а не на шифрование);
- per-char: ~2.7–3.0 мкс (~350k chars/s);
- на символ: ~12 method calls (press/_step/at_notch/step/_plug×2/
  forward×3/reflect/backward×3), ~25 attribute lookups, per-char
  str/ord/chr/dict.get, `ch in ALPHABET` (substring search), list.append.

Архитектура (`fast_enigma.py`, reference `enigma.py` — только для
correctness/tests/vectors/differential; fast — только массовый evaluation):
- ints внутри (A=0..Z=25): `encode_text` один раз, `decode_ints` один раз;
- таблицы `FWD/BWD[pos][c]` на (ротор, кольцо) из данных core
  (проводки/engagement — без дублирования констант);
- stepping ПЕРЕД символом, notch/double-step/ring/order/reflector/stepping
  по модели — как core (доказано differential);
- per-candidate setup = `set_positions()` (инты), без reconstruction;
- без глобального mutable state: таблицы immutable после build, mutable —
  только позиции инстанса (один инстанс = один поток, как reference);
- M4: греческий статичен, но в тракте; K/D: UKW-таблица свёрнута один раз
  на build; G: carry-шаг отдельным ясным (не горячим) путём.

Что было оптимизировано (по измерению, не на глаз): убрана construction из
sweep + заинлайнен рычажный шаг (без per-char method call) + локальные
таблицы/маски/позиции + списки вместо dict.get/str-операций.

Differential results (`tests/test_fast_differential.py`, seed фиксирован,
normal output чистый, при failure — полный дамп):
- M3: 30 random конфигов (роторы I–VIII, кольца, штекеры 0–10) × длины
  1/5/50/300/1000 — fast == own core побайтово + позиции после прогона;
- M4: 30×5 аналогично (Beta/Gamma, Thin-B/C);
- I: 20×2 (роторы I–V, UKW A/B/C);
- G/G312/G260/K/D: 20 конфигов × 2 длины vs own core (внешнего эталона нет —
  external differential НЕ заявляется) + G step-таблица NZAM→ODGW incl.
  Lobster через fast-позиции + roundtrip;
- прямая сверка fast vs py-enigma 1.0.2: 10 random M-line (транзитивность
  own==ref + fast==own).

Benchmark results (warmup + 5–7 reps + median/min/max, M3 II IV V/B/BUL/BUO
+ 10 plugs; current vs fast на одинаковом конфиге/шифре/диапазоне):
- construction: ref median 0.05ms / fast 0.47ms (таблицы строятся дольше —
  цена разовая, окупается в sweep; зафиксировано честно);
- single decrypt (9 букв): ref 0.12ms / fast 0.01ms (~10x);
- long 20k: ref 354k chars/sec / fast 2 071k chars/sec (5.8x);
- sweep 676 позиций × 9 букв: ref 12 974 pos/sec (117k chars/sec) /
  fast 211 257 pos/sec (1 901k chars/sec) — speedup 16.3x;
- decrypt+score (195 букв): ref 183k / fast 676k chars/sec (3.7x).
- Scorer status: 3.27M chars/s против combined fast 676k — scorer пока НЕ
  bottleneck (запас ~5x, был ~15x). Scoring optimization — отдельная Phase
  по факту замера, не сейчас (§11 соблюдён).

Tests: 12 новых (7 differential + 5 bench smoke с assert fast<ref) — все PASS.
Regression: pytest 82/82 + core 32/32 + vectors 17/17 + keydb ALL OK +
legacy ALL OK + OCR 29/29 + GUI 9/9 (без изменений) + CLI.

Known limitations:
- FastEnigma — experimental evaluator для будущего search, не проверенный
  десятилетиями core; исторические векторы гоняются на reference.
- G/K/D differential (external) = OPEN, без изменений; fast их покрывает
  только vs own core — ложного ощущения исправления не создаём.
- Production corpus: test-only (без изменений).
- Один инстанс FastEnigma на поток; отмена — снаружи (sweep-цикл вызывающего).

STOP: hill climbing / annealing / plugboard optimizer / GPU /
multiprocessing / full brute force / production Crack UI — НЕ начаты.
Остаточный bottleneck: симуляция Enigma (~2M chars/s single-core Python) —
следующая Phase 9 решает, чем её кормить (search strategy), а не как ещё
разогнать цикл: ускорение 16x уже на столе как основа cryptanalytic search.

## Phase 9

Статус: search landscape измерен, ответ на ключевой вопрос получен.
Production CrackerEngine NOT implemented. ABC/FastEnigma/Scorer/xcracker
не менялись. GUI/OCR/KeyDB/MachineSpec не менялись. G/K/D differential
остаётся OPEN. Single-process/single-thread (по ограничению этапа).

Маркировка: все результаты — TEST SCORER (unit тетраграммная модель),
NOT REPRESENTATIVE OF REAL HISTORICAL CRYPTANALYSIS.

Framework (`search_experiments.py`, отдельный модуль):
- Benchmark corpus: deterministic synthetic generator (`make_case`:
  seeded German-like текст из test-лексики + known config → шифр
  reference core). Random deterministic configs — шаблон + seed, не только
  исторические ключи. Case хранит plaintext/ciphertext/machine/rotors/
  reflector/rings/positions/plugboard.
- `PositionEvaluator`: один подготовленный FastEnigma + `set_positions`
  на candidate (без reconstruction), счётчик evaluations, `bind(cipher)`
  один раз.
- Стратегии — отдельные объекты, ABC не тронут: `PositionHillClimber`,
  `RandomPositionSearch`, `SimulatedAnnealer` (пресеты fast/slow,
  geometric schedule, deterministic RNG), `multi_start`,
  `exhaustive_search`, `analyze_landscape`, `length_table`.
- Plugboard/rotors/rings фиксированы (Phase 9A): ищутся только positions.

Landscape analysis (M3 II IV V/B/BUL/10 plugs, TEST SCORER):
- Истина — строгий изолированный пик: improving_1 = 0/6 на длинах
  50/100/200/500/1000/2000 (таблица §13: true ≈ −3.2 length-invariant,
  mean neighbour ≈ −4.7, best neighbour ≈ −4.7, margin ≈ 1.5).
- Второе кольцо: 18 уникальных позиций (6 одноосевых + 12 двухосевых).
- P(улучшающий сосед | random state) ≈ 0.60 (n=200) — локальная структура
  есть везде, но это шум: жадный подъём застревает в среднем за ~2 итерации.
- Вывод: локального gradient к истине НЕТ (golf-course-with-noise).

Benchmark report (M3, fixed всё кроме positions, 26^3 = 17576):
- exhaustive len=200: true rank 1/17576, margin 1.480, ~5.6k pos/sec, 3.1s;
  len=50: rank 1/17576, 0.8s. Top-1/5/20 = истина везде. Scorer различает
  правильный key уже с ~50 символов (на TEST SCORER).
- hill climbing multi-start 50 starts: success 0/50, avg iter ~1.9.
- random search (2000/17576, 10 seeds): истина всегда rank 1 ЕСЛИ в выборке,
  но P(попадания) ≈ 11% — как поиск не работает лучше перебора.
- SA fast/slow presets, 10 starts: success 0/10 и 0/10.
- Итог стратегий: exhaustive дёшев (~секунды) и оптимален на 26^3;
  local/random/annealing не дают ничего сверх перебора.

КЛЮЧЕВОЙ РЕЗУЛЬТАТ (ответ без выводов заранее):
При фиксированных rotor/reflector/ring/plugboard найти positions БЕЗ
exhaustive 26^3 локальным поиском НЕЛЬЗЯ (0/50 hill, 0/10 SA) — но это
не проблема: exhaustive стоит ~1–3 секунды. Positions-only задача
фактически РЕШЕНА перебором; настоящая сложность — rings/rotors/plugs
(следующие фазы). Расширять пространство — постепенно, crib/scorer —
только если понадобится.

Tests: 17 новых (known-answer ×2, exhaustive ×3, hillclimb ×3, random ×2,
SA ×3, landscape ×2) — все PASS. Regression: pytest 99/99 + core 32/32 +
vectors 17/17 + keydb ALL OK + legacy ALL OK + OCR 29/29 + GUI 9/9 (без
изменений) + CLI.

Known limitations:
- Всё на TEST SCORER; production corpus по-прежнему OPEN.
- SA-пресеты не подбирались (по ограничению этапа) — результат 0/10
  относится к пресетам fast/slow, не к SA вообще.
- G/K/D differential (external) = OPEN, без изменений.

STOP: plugboard optimization / unknown rotor order / unknown rings /
crib attack / full M3 / M4 / multiprocessing / GPU / GUI Crack — НЕ начаты.
