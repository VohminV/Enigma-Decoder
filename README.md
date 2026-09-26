# Enigma Decoder

> [!WARNING]
> **Enigma — исторический/образовательный шифр, взломанный ещё в 1940-х годах
> и тривиально вскрываемый современным компьютером за минуты.**
> Этот проект — дешифратор для изучения истории, исследований перехватов
> и обучения. **Не используйте Enigma для защиты реальных конфиденциальных
> данных, паролей, личной переписки или коммерческих секретов.**
> Для реальной защиты используйте современную криптографию
> (AES-256-GCM, ChaCha20-Poly1305, TLS 1.3).

Дешифратор Enigma I / M3 / M4 / G / K / D с GUI (PySide6), базой суточных ключей и OCR для перехватываемых шифротекстов.

Симметричность: расшифровка = шифровка при тех же настройках.

## Поддерживаемые машины

Статус проверки: **M-line (I/M3/M4) — validated** (исторические векторы +
differential против `py-enigma 1.0.2`); **G/K/D — experimental /
internal-verified** (roundtrip + таблицы `Examples/Notches`, внешнего
побайтового эталона нет; при использовании ядро выдаёт `UserWarning`).

M-line (рычажный шаг, двойной шаг среднего ротора, ETW = алфавит):

- **Enigma I (Heer/Luftwaffe)**: роторы I–V (3 шт.), UKW A/B/C, штекеры (до 10 пар).
- **Enigma M3 (Kriegsmarine)**: роторы I–VIII, UKW B/C, штекеры.
- **Enigma M4 (U-Boat)**: греческий Beta/Gamma (статичен, не шагает) + 3 ротора I–VIII, тонкие UKW Thin-B/Thin-C, штекеры.
  - Совместимость: `Beta + Thin-B @ A == толстый B`, `Gamma + Thin-C @ A == толстый C` (проверено в `test_vectors.py`).

- **Enigma G (Abwehr, Zählwerk)** *(experimental)*: колёса I–III (варианты проводки `G` / `G312` / `G260`), подвижный UKW с кольцом, ETW = QWERTZ, без штекеров, шестерёночный carry-шаг без двойного шага.
- **Commercial K (A27) / D (A26)** *(experimental)*: коммерческая проводка, settable неподвижный UKW с кольцом, ETW = QWERTZ, без штекеров, обычный рычажный шаг. Engagement: K = Y/E/N; D = notch на корпусе (`Y + ring`).

Проводки: NSA wiring catalog (Hammarborg/Weierud), cryptomuseum, Hamer.

## Быстрый старт

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"   # или: pip install PySide6 rapidocr pymupdf Pillow numpy opencv-python
python main.py
```

OCR-модели (PP-OCRv6, ONNX) идут в комплекте пакета `rapidocr`
(`site-packages/rapidocr/models`) — скачивание не требуется, работа offline.

Проверки: новые pytest-тесты — `python -m pytest` (игнорирует script-style
файлы через `conftest.py`); классические сюиты — напрямую, см. «Проверки» ниже.

Лог GUI: `enigma_gui.log` рядом с программой.

## Использование

### GUI (`python main.py`)

Страницы (sidebar слева):

- **Decrypt** — ручная шифровка/расшифровка. Вставить CIPHERTEXT, выбрать машину, `Decrypt` (`Ctrl+Enter`).
- **Crack** — индикатор-солвер (реален, мгновенно: ключ сообщения = расшифровка индикатора на Grundstellung) + исторический поиск по базе (реален, в worker-потоке). Полный автоматический поиск — `Not implemented` (кнопка отключена).
  - Custom ciphertext: каждая конфигурация выбранной даты расшифровывает твой перехват — так проверяются чужие сообщения вроде SHARK без ключа дня (читаемый немецкий текст = попадание).
- **OCR** — image/PDF → preprocessing → RapidOCR (PP-OCRv6, ONNX CPU, 100% offline) → normalize → `Send to Decrypt / Crack`. Исходник не мутирует. Batch и PDF поддерживаются.
- **Keys** — поиск по базе (`keys.json`), детали, `Use Configuration` / `Decrypt`, импорт/экспорт JSON, редактор записей с валидацией через построение машины.
- **Machine** — диагностика состояния роторов + пошаговый тест (`Build / Reset`, `Step`, по одной букве).
- **Benchmark** — замер ядра (реален: M3/M4 chars/sec, positions sweep) и OCR на синтетике (реален). Fast/Cracker — `Not implemented`.
- **Settings** — тема (Dark/System), потоки (резерв под cracker Phase 7+), путь к базе, OCR-профиль/политика. Хранение — `QSettings`.

### CLI ядра (`enigma.py`)

```powershell
# M3
python enigma.py --model M3 --rotors I II III --reflector B --rings AAA --positions AAA --text BDZGO
# -> AAAAA

# M4, реальное сообщение U-264 (1942): Thin-B, Beta II IV I, кольца AAAV, старт VJNA
python enigma.py --model M4 --rotors Beta II IV I --reflector Thin-B --rings AAAV --positions VJNA --plugs "AT BL DF GJ HM NW OP QY RZ VX" --text "NCZW VUSX ..." --group5

# G
python enigma.py --model G312 --rotors III II I --rings AAAA --positions NZAM --text HELLO

# K
python enigma.py --model K --rotors I II III --rings AAA --positions AAA --text HELLO
```

Опции: `--in` / `--out` файлы, `--group5` группировка по 5, `--ukw-pos` / `--ukw-ring` для K/D (позиция/кольцо UKW), для G — 4 буквы rings/positions `[UKW,L,M,R]`.

### База ключей (`keydb.py`, `keys.json`)

```powershell
python keydb.py list
python keydb.py show 1945-05-01
python keydb.py show km-1945-05-01-potsdam
python keydb.py verify
python keydb.py verify --id km-1945-05-01-potsdam
python keydb.py decrypt --id km-1945-05-01-potsdam --msg P1030684
```

Формат записи: `date/model/network/wheels/greek/reflector/rings (+rings_alt)/plugs/messages`. Уровни проверки сообщений: `indicator` (индикатор@Grundstellung → ключ), `full` (весь текст), `prefix` (начало), `none`. Статус записи: `verified` (проверено движком) / `published` (опубликовано, тестового сообщения с известным ключом пока нет).

Текущее покрытие: `1941-07-07`, `1941-07-13` (M3 Heer), `1945-04-30`, `1945-05-01` (M4 Potsdam/U-534), `1945-05-02` (published, без шифротекста).

### Процедура Kriegsmarine (для чтения перехватов)

Морские сообщения идут 4-буквенными группами. Первые/последние группы — Kenngruppen + индикатор, в тело не входят (например, в приказе Дёница P1030681 первые 2 и последние 2 группы — индикатор `DUHF TETO`, в шифротекст базы не включены).

Схема: `message key --(шифр на Grundstellung)--> indicator --(передача с Kenngruppen)--> получатель расшифровывает indicator на Grundstellung --> message key --> расшифровка тела на message key`.

Пример из базы: `QEOB @ NAEM -> CDSZ` (индикатор → ключ), далее тело на `CDSZ`.

Если повторяется `первые 2 группы == последние 2 группы` (как `CXSO UNVZ ... CXSO UNVZ` в SHARK-тесте: 90 групп / 360 букв / тело 344) — это Kenngruppen-рамка, для взлома нужно тело + суточный ключ дня (Walzenlage, Ringstellung, Stecker, Grundstellung).

## Проверки

```powershell
python tests/test_core.py     # свойства компонентов: notch, рефлекторы, штекеры, double-step, сброс
python tests/test_vectors.py  # исторические векторы: M3 sanity, M4 U-264, M4 Dönitz P1030681 + индикатор, Enigma I 1930, шаг G, roundtrip K/D
python tests/test_keydb.py    # проверка базы движком (verified only) + инварианты
python tests/test_gui.py      # GUI без окна: sidebar, Decrypt, OCR normalize, crack worker
python legacy.py        # файлы симулятора Enigma 1.x из Examples/: DoubleStep, Notches M4/G, Wetter M3==M4, Dönitz ASTV
python tools/evaluate_ocr.py  # оценка OCR (при наличии данных)
python -m pytest       # pytest-сюиты: specs 8 моделей, benchmark, validation,
                       # atomic writes, workers/shutdown, differential vs py-enigma,
                       # contracts, scoring, experimental cracker, fast enigma,
                       # search experiments
```

Все вышеперечисленное на момент релиза: `ALL OK` (pytest: 52 passed).

## Структура

```
main.py              точка входа GUI
enigma.py            ядро I/M3/M4/G/K/D + CLI
keydb.py             база суточных ключей (просмотр/проверка/расшифровка)
services.py          слой GUI->ядро (сборка конфигов, historical lookup, benchmark)
keys.json            база ключей (version 1)
gui/                 MainWindow, pages (Decrypt/Crack/OCR/Keys/Machine/Benchmark/Settings), widgets, workers, dialogs
ocr/                 pipeline, engine (RapidOCR), preprocessing, postprocessing, models, worker
Examples/            Arthur's, Dönitz, DoubleStep, Notches, Wetter
tools/evaluate_ocr.py
test_*.py            тесты (см. Проверки)
```

## Ограничения (честно)

- Full automatic search (CrackerEngine, hillclimb/бомба по plugs/rings/rotors без ключа) — `Not implemented` (Phase 7+). Исторический поиск находит только то, чей суточный ключ уже есть в `keys.json`.
- DoS-лимиты релиза 1.0.0: текст — 1 000 000 символов (`enigma.MAX_TEXT_CHARS`), входной файл — 5 МБ (`enigma.MAX_FILE_BYTES`), база ключей — 10 МБ, изображение — 50 МП / 30 МБ, PDF DPI — 72..400, `positions_sweep` — 100 000 вариантов. Превышение даёт понятную ошибку `ValueError` без stack trace в GUI.
- M-line роторы не должны повторяться (один физический ротор — один слот); `press()` принимает строго одну букву A-Z.
- G/K/D: engagement-таблицы и часть проводок — внутренние таблицы проекта (roundtrip + Examples/Notches), внешнего побайтового эталона нет. Для M-line есть differential против `py-enigma 1.0.2`.
- OCR — только латинская модель; готика/рукописный текст и сильные искажения скана дают низкую уверенность (подсветка блоков < 0.6 в GUI).
- Тонкие рефлекторы только для M4; VI–VIII запрещены для Enigma I (валидация бросает `ValueError` с понятным текстом).

## Безопасность

- Локальное приложение без сети/auth: сетевые риски (XSS/CSRF/SSRF/SQLi/CORS) неприменимы. Не выставляйте GUI/CLI как сетевой сервис без отдельной изоляции, auth и rate-limit.
- Логи (`enigma_gui.log`, ротация 1 МБ × 3) не содержат ключей/колец/штекеров/текстов — только типы ошибок. Детали конфигурации показываются только пользователю в диалоге.
- Секретов в репозитории нет; исторические ключи `keys.json` — публичные архивные данные.
- Подробнее: `SECURITY.md`.

## Источники векторов

- U-264 (25.11.1942, M4 Project / Erskine 1995)
- P1030681/P1030684/P1030725 (U-534, hoerenberg.com, cryptomuseum.com)
- Enigma I 1930 (Schlüsselanleitung), G-таблицы шага (Examples/Notches)
- Heer 1941 (rostfrank.de)
