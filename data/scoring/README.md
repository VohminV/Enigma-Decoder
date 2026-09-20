# Scoring data

Runtime использует **подготовленную** n-gram модель, сырой корпус в runtime
не нужен и ничего не скачивается автоматически.

## Текущий статус

- `test_corpus.txt` — маленький deterministic корпус ТОЛЬКО для unit tests
  (военная лексика, ~70 слов). **Не является production языковой моделью.**
- `test_tetragrams.json` — собранная из него тестовая модель
  (`python tools/build_scorer.py --corpus data/scoring/test_corpus.txt
  --order 4 --out data/scoring/test_tetragrams.json`).
- Production-корпус: **TODO (OPEN)**.

## Production TODO

1. Найти подходящий локальный источник немецкого текста 1930–1945
   (военные донесения, public domain) и зафиксировать источник + лицензию.
2. Нормализовать (A-Z, umlaut→AE/OE/UE, ß→SS — отдельным скриптом,
   не трогая `scoring.normalize_for_scoring`).
3. Собрать модель: `python tools/build_scorer.py --corpus <file>
   --order 4 --out data/scoring/de_tetragrams.json`.
4. Замерить разделимость (natural vs random) и записать в `docs/AUDIT.md`.
5. Не коммитить сырые корпуса тяжелее ~1 МБ без решения (модель — можно).

## Формат модели

JSON: `{"name", "order", "floor", "log_probs": {tetragram: log10 prob}}`.
Поле `floor` — log-вероятность невиданной n-граммы. Детерминирован
(`sort_keys=True` при записи).
