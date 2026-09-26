# Architecture — Enigma Decoder v1.0.0

## Компоненты

```text
GUI (gui/, PySide6) ──только через services──▶ Services (services.py)
                                                 ├─▶ Core (enigma.py: EnigmaMachine/EnigmaG/EnigmaCommercial)
                                                 ├─▶ Data (keydb.py + keys.json)
                                                 └─▶ OCR (ocr/pipeline.py → preprocessing → engine → postprocessing)
Experimental: scoring.py + contracts.py + xcracker.py + fast_enigma.py + search_experiments.py
Entry points: main.py (GUI), enigma.py (CLI), keydb.py (CLI), legacy.py (Examples-проверка)
```

## Data flow

1. Ввод: QTextEdit / MachineWidget / QFileDialog / CLI args / QSettings / JSON-файлы.
2. Валидация: `MachineSpec` + `_check_letters` + `parse_plugs` + `validate_dimensions` + `keydb.validate_entry`.
3. Обработка: `press()` (stepping ДО символа) / OCR в `QThread` / benchmark в worker.
4. Вывод: QTextEdit / QMessageBox (понятные `ValueError`) / stdout-файлы CLI.
5. Логи: `enigma_gui.log` (ротация, только типы ошибок, без key-material).
6. Хранение: `keys.json` целиком в память, `QSettings` (UI-предпочтения), export/import через `atomic_write_json`.

## Trust boundaries

- Доверенное: собственный код, `keys.json` из репозитория, исторические векторы.
- Недоверенное: вставляемый cipher-текст, импортируемый JSON, изображения/PDF,
  CLI `--in` файлы, OCR-выход, scorer-модели. Всё проходит лимиты размера
  и схемную валидацию до обработки.
- Локальный single-user: нет сетевой границы; файлы читаются/пишутся только
  по явному выбору пользователя. Сетевого API нет — при его появлении
  потребуется новая граница (auth/rate-limit/изоляция).

## Crypto state

- Состояние машины = только позиции роторов (+ UKW-позиция для G).
- Нет глобального mutable state; инстансы независимы; `reset()` восстанавливает старт.
- `FastEnigma`: таблицы immutable после build, mutable — только позиции
  (один инстанс = один поток, как reference).
- Симметричность: `decipher = encipher`; stepping/double-step/ring-offset
  покрыты векторами + differential M-line против `py-enigma 1.0.2`.

## Extension points

- `contracts.Scorer` / `contracts.CrackerEngine` — будущий поиск без переделки GUI.
- `MachineSpec` — единая размерность для CLI/GUI/БД (новые модели — через Spec).
- OCR-движки — через `OCREngine.recognize()`; uncertainty — через `OCRCharacter`.
