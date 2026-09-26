#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка n-gram модели скорера из локального корпуса (reproducible).

Ничего не скачивает: корпус — локальный текстовый файл.
Использование:
  python tools/build_scorer.py --corpus data/scoring/test_corpus.txt \\
      --order 4 --out data/scoring/test_tetragrams.json
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import scoring  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Сборка n-gram модели скорера")
    p.add_argument("--corpus", required=True, help="локальный текстовый файл")
    p.add_argument("--order", type=int, default=4, help="порядок n-грамм 1..4")
    p.add_argument("--out", required=True, help="выходной JSON модели")
    p.add_argument("--name", default=None, help="имя модели")
    args = p.parse_args(argv)
    if not 1 <= args.order <= 4:
        print("order должен быть 1..4", file=sys.stderr)
        return 2
    try:
        with open(args.corpus, encoding="utf-8") as f:
            raw = f.read()
    except OSError as ex:
        print(f"Не могу прочитать корпус: {ex}", file=sys.stderr)
        return 1
    counts = scoring.count_ngrams(raw, args.order)
    if not counts:
        print("Корпус пуст после нормализации", file=sys.stderr)
        return 1
    table, floor = scoring.log_probs_from_counts(counts)
    name = args.name or ("tetragram" if args.order == 4 else f"{args.order}-gram")
    if args.order == 4:
        model = scoring.TetragramScorer(table, floor, name)
    else:
        model = scoring.NGramScorer(args.order, table, floor, name)
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    model.save(args.out)
    print(f"order={args.order} grams={len(table)} floor={floor:.3f} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
