#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка базы суточных ключей движком. Запуск: python test_keydb.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from keydb import find, load_db, verify_entry  # noqa: E402

entries = load_db()
all_ok = True
for e in entries:
    if e["status"] != "verified":
        print(f"{e['id']}: SKIP (status={e['status']})")
        continue
    ok, report = verify_entry(e)
    all_ok &= ok
    print(f"[{'OK' if ok else 'FAIL'}] {e['id']} ({e['date']})")
    for line in report:
        print(line)

# База обязана содержать записи начиная с 1940 г.
dates = sorted(e["date"] for e in entries)
assert dates and all(d >= "1940-01-01" for d in dates), dates
# Каждая verified-запись обязана иметь хотя бы одно проверяемое сообщение
for e in entries:
    if e["status"] == "verified":
        assert any(m.get("verified") in ("indicator", "full", "prefix")
                   for m in e["messages"]), e["id"]
# Точечная проверка поиска
assert find(entries, "1941-07-07")["id"] == "heer-1941-07-07"
assert find(entries, "km-1945-05-01-potsdam")["date"] == "1945-05-01"

print("KEYDB ALL OK" if all_ok else "KEYDB SOME FAILED")
sys.exit(0 if all_ok else 1)
