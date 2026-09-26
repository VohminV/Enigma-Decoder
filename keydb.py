#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""База суточных ключей Enigma (с 1940 г.): просмотр и проверка движком.

Использование:
  python keydb.py list                       — все записи
  python keydb.py show <id|date>             — карточка ключа
  python keydb.py verify [--id <id>]         — проверить записи движком
  python keydb.py decrypt --id <id> --msg <mid>
                                             — расшифровать сообщение из базы

Статусы записей: verified (проверено движком), published (опубликовано,
тестового сообщения с известным ключом в базе пока нет).
Уровни проверки сообщений: indicator / full / prefix / none.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from enigma import (EnigmaCommercial, EnigmaG, EnigmaMachine,  # noqa: E402
                    normalize_reflector, normalize_rotor, parse_plugs,
                    spec_for)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys.json")


def resolve_db_path(path: str | None = None) -> str:
    """Путь к базе: явный аргумент > ENIGMA_KEYS_PATH > рядом с модулем > CWD.

    Нужно для wheel-установок, где keys.json может лежать рядом с модулем
    (editable/sdist) или задаваться окружением.
    """
    if path:
        return path
    env = os.environ.get("ENIGMA_KEYS_PATH", "").strip()
    if env:
        return env
    alongside = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "keys.json")
    if os.path.exists(alongside):
        return alongside
    cwd = os.path.join(os.getcwd(), "keys.json")
    return cwd if os.path.exists(cwd) else alongside

# DoS-защита: база читается целиком (по дизайну плоский JSON на 5 записей).
MAX_DB_BYTES = 10_000_000


def atomic_write_json(path: str, data: dict) -> None:
    """Атомарная запись JSON (AUD-007): временный файл в том же каталоге
    -> flush + fsync -> os.replace (атомарно на Windows в пределах тома).
    Crash mid-write не портит целевой файл; мусор tmp чистится."""
    import tempfile
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp_keys_",
                               suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED_ENTRY_FIELDS = ("id", "date", "model", "wheels", "rings", "status")
_MESSAGE_LEVELS = ("indicator", "full", "prefix", "none")


def _letters(s: str) -> bool:
    return bool(s) and all("A" <= c <= "Z" for c in s)


def validate_entry(entry: dict) -> list[str]:
    """Проверить запись базы. Возвращает список ошибок (пусто = валидна).

    Ничего не исправляет молча: каждая проблема — явная строка с
    Expected/Received там, где это применимо (AUD-006).
    """
    errs: list[str] = []
    if not isinstance(entry, dict):
        return ["entry must be an object"]
    eid = entry.get("id", "?")
    for f in _REQUIRED_ENTRY_FIELDS:
        if f not in entry:
            errs.append(f"{eid}: missing required field '{f}'")
    if errs:
        return errs

    model = entry.get("model")
    try:
        spec = spec_for(model)
    except ValueError:
        return [f"{eid}: unknown model {model!r}"]

    date = entry.get("date", "")
    if not isinstance(date, str) or not _DATE_RE.match(date):
        errs.append(f"{eid}: bad date {date!r}. Expected:\nYYYY-MM-DD")
    else:
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            errs.append(f"{eid}: non-existent calendar date {date!r}")

    if entry.get("status") not in ("verified", "published"):
        errs.append(f"{eid}: bad status {entry.get('status')!r}. "
                    "Expected:\nverified | published")

    wheels = entry.get("wheels", [])
    if not isinstance(wheels, list) or not all(isinstance(w, str) for w in wheels):
        errs.append(f"{eid}: wheels must be a list of strings")
        wheels = []
    else:
        for w in wheels:
            try:
                normalize_rotor(w)
            except ValueError:
                errs.append(f"{eid}: unknown rotor {w!r}")
        allowed: set[str] = set()
        for opts in spec.wheel_options:
            allowed |= set(opts)
        if entry.get("model") == "M4":
            allowed |= {"Beta", "Gamma"}
        for w in wheels:
            try:
                name = normalize_rotor(w)
            except ValueError:
                continue
            if name not in allowed and name not in ("BETA", "GAMMA"):
                errs.append(f"{eid}: rotor {w!r} not allowed for {spec.model}")
        if spec.distinct_wheels and len(set(wheels)) != len(wheels):
            errs.append(f"{eid}: wheels must be distinct. Received:\n"
                        + " ".join(wheels))

    greek = entry.get("greek")
    if spec.model == "M4":
        if greek not in ("Beta", "Gamma"):
            errs.append(f"{eid}: M4 requires greek Beta|Gamma. Received:\n{greek!r}")
    elif greek is not None:
        errs.append(f"{eid}: greek rotor only valid for M4, "
                    f"not {spec.model}. Received:\n{greek!r}")

    refl = entry.get("reflector", "")
    if spec.reflectors:
        try:
            canon = normalize_reflector(refl)
        except ValueError:
            errs.append(f"{eid}: unknown reflector {refl!r} for {spec.model}")
            canon = None
        allowed_refl = {r.upper() for r in spec.reflectors}
        if canon is not None and canon.upper() not in allowed_refl:
            errs.append(f"{eid}: reflector {refl!r} not allowed for {spec.model}. "
                        f"Expected:\n{' | '.join(spec.reflectors)}")
    elif refl:
        errs.append(f"{eid}: model {spec.model} has no reflector. Received:\n{refl!r}")

    rings = entry.get("rings", "")
    if not isinstance(rings, str) or not _letters(rings) or len(rings) != spec.rings:
        errs.append(f"{eid}: bad rings {rings!r}. Expected:\n"
                    f"{spec.rings} letters A-Z")
    for alt in entry.get("rings_alt", []) or []:
        if not isinstance(alt, str) or not _letters(alt) or len(alt) != spec.rings:
            errs.append(f"{eid}: bad rings_alt entry {alt!r}. Expected:\n"
                        f"{spec.rings} letters A-Z")

    try:
        parse_plugs(entry.get("plugs", "") or "")
    except ValueError as ex:
        errs.append(f"{eid}: bad plugboard: {ex}")

    messages = entry.get("messages", [])
    if not isinstance(messages, list):
        errs.append(f"{eid}: messages must be a list")
        return errs
    seen_msgs: set[str] = set()
    for m in messages:
        if not isinstance(m, dict):
            errs.append(f"{eid}: message must be an object")
            continue
        mid = m.get("id", "?")
        if mid in seen_msgs:
            errs.append(f"{eid}/{mid}: duplicate message id")
        seen_msgs.add(mid)
        level = m.get("verified", "none")
        if level not in _MESSAGE_LEVELS:
            errs.append(f"{eid}/{mid}: bad verified level {level!r}")
            continue
        for field, want in (("key", spec.positions),
                            ("grundstellung", spec.positions),
                            ("indicator", None)):
            val = m.get(field)
            if field == "key" and level in ("indicator", "full", "prefix") and val is None:
                errs.append(f"{eid}/{mid}: level {level} requires 'key'")
            if field == "grundstellung" and level == "indicator" and val is None:
                errs.append(f"{eid}/{mid}: level indicator requires 'grundstellung'")
            if field == "indicator" and level == "indicator" and val is None:
                errs.append(f"{eid}/{mid}: level indicator requires 'indicator'")
            if val is None:
                continue
            # '?' в grundstellung/indicator — документированный маркер
            # ненадёжной транскрипции источника (см. spruch-24a: источник
            # misprints Grundstellung/indicator; движок эти поля не использует,
            # уровень проверки — full по key/cipher). В key/позициях '?' запрещён.
            check_val = val
            if field in ("grundstellung", "indicator") and "?" in val:
                check_val = val.replace("?", "")
                if not check_val:
                    errs.append(f"{eid}/{mid}: bad {field} {val!r}. "
                                "Expected:\nletters A-Z (? allowed)")
                    continue
            if not isinstance(val, str) or not _letters(check_val):
                errs.append(f"{eid}/{mid}: bad {field} {val!r}. "
                            "Expected:\nletters A-Z")
            elif (want is not None and _letters(check_val)
                    and len(check_val) != want):
                errs.append(f"{eid}/{mid}: bad {field} length. Expected:\n"
                            f"{want} letters\n\nReceived:\n{len(check_val)}")
        if level in ("full", "prefix") and not m.get("cipher"):
            errs.append(f"{eid}/{mid}: level {level} requires 'cipher'")
        if level == "full" and not m.get("plain"):
            errs.append(f"{eid}/{mid}: level full requires 'plain'")
        if level == "prefix" and not m.get("plain_prefix"):
            errs.append(f"{eid}/{mid}: level prefix requires 'plain_prefix'")

    # Сквозная проверка размерности через единый MachineSpec (M3 ≠ M4:
    # 3 vs 4 колеса/кольца ловятся здесь одной строкой).
    if isinstance(wheels, list):
        n_wheels = len(wheels) + (1 if entry.get("model") == "M4" else 0)
        if n_wheels != spec.wheels:
            errs.append(
                f"{eid}: wrong wheel count for {spec.model}. Expected:\n"
                f"{spec.wheels} wheels\n\nReceived:\n{n_wheels}")
    return errs


def validate_db(entries: list) -> dict[str, list[str]]:
    """Проверить всю базу. Возвращает {id: [ошибки]} только для битых."""
    bad: dict[str, list[str]] = {}
    seen: set[str] = set()
    if not isinstance(entries, list):
        return {"<db>": ["database root must be a list of entries"]}
    for e in entries:
        eid = e.get("id", "?") if isinstance(e, dict) else "?"
        errs = validate_entry(e)
        if eid in seen:
            errs = errs + [f"{eid}: duplicate entry id"]
        seen.add(eid)
        if errs:
            bad[eid] = errs
    return bad


def load_db(path: str | None = None) -> list[dict]:
    resolved = resolve_db_path(path)
    size = os.path.getsize(resolved)
    if size > MAX_DB_BYTES:
        raise ValueError(
            f"База слишком большая: {size} байт (лимит {MAX_DB_BYTES})."
        )
    with open(resolved, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("bad format: корень — объект с полем 'entries' (список)")
    return data["entries"]


def find(entries: list[dict], ident: str) -> dict:
    ident = ident.strip()
    for e in entries:
        if e["id"] == ident or e["date"] == ident:
            return e
    raise KeyError(f"Запись {ident!r} не найдена")


def build_machine(entry: dict, positions: str):
    """Собрать движок под модель записи, установив позиции."""
    model = entry["model"]
    if model in ("I", "M3", "M4"):
        rotors = list(entry["wheels"])
        rings = entry["rings"]
        if model == "M4":
            rotors = [entry["greek"]] + rotors
        return EnigmaMachine(tuple(rotors), entry["reflector"], rings,
                             positions, entry.get("plugs", ""), model=model)
    if model in ("G", "G312", "G260"):
        return EnigmaG(entry.get("variant", model), tuple(entry["wheels"]),
                       entry["rings"], positions)
    if model in ("K", "D"):
        return EnigmaCommercial(model, tuple(entry["wheels"]), entry["rings"],
                                positions, entry.get("ukw_pos", "A"),
                                entry.get("ukw_ring", "A"))
    raise ValueError(f"Неизвестная модель: {model!r}")


def verify_message(entry: dict, msg: dict) -> tuple[bool, str]:
    """Проверить одно сообщение. Возвращает (ok, пояснение)."""
    level = msg.get("verified", "none")
    if level == "none":
        return True, "skip (no test data)"
    if level == "indicator":
        m = build_machine(entry, msg["grundstellung"])
        got = m.decipher(msg["indicator"])
        ok = got == msg["key"]
        return ok, f"indicator {msg['indicator']}@{msg['grundstellung']} -> {got}"
    if level in ("full", "prefix"):
        m = build_machine(entry, msg["key"])
        got = m.decipher(msg["cipher"])
        if level == "full":
            ok = got == msg["plain"]
            return ok, f"full text {len(got)} chars, match={ok}"
        ok = got.startswith(msg["plain_prefix"])
        return ok, f"prefix {msg['plain_prefix'][:40]}..., match={ok}"
    raise ValueError(f"Неизвестный уровень проверки: {level!r}")


def verify_entry(entry: dict) -> tuple[bool, list[str]]:
    report: list[str] = []
    ok_all = True
    for msg in entry.get("messages", []):
        try:
            ok, note = verify_message(entry, msg)
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"exception: {e}"
        ok_all &= ok
        report.append(f"  [{'OK' if ok else 'FAIL'}] {msg['id']}: {note}")
    return ok_all, report


def cmd_list(entries: list[dict]) -> int:
    for e in entries:
        wheels = " ".join(e["wheels"])
        greek = (e.get("greek") or "") + " " if e.get("greek") else ""
        print(f"{e['date']}  {e['id']:28s} {e['model']:4s} {e.get('reflector',''):7s} "
              f"{greek}{wheels:12s} [{e['status']}]")
    return 0


def cmd_show(entries: list[dict], ident: str) -> int:
    e = find(entries, ident)
    print(f"{e['id']}  ({e['date']}, {e['service']}, {e.get('network','')})")
    print(f"  model: {e['model']}, reflector: {e.get('reflector')}, "
          f"greek: {e.get('greek')}, wheels: {' '.join(e['wheels'])}")
    print(f"  rings: {e['rings']}"
          + (f"  (also listed: {', '.join(e['rings_alt'])})" if e.get("rings_alt") else ""))
    print(f"  plugs: {e.get('plugs') or '-'}")
    print(f"  status: {e['status']}")
    if e.get("notes"):
        print(f"  notes: {e['notes']}")
    for m in e.get("messages", []):
        print(f"  msg {m['id']}: key={m.get('key')} verified={m.get('verified')}")
        if m.get("notes"):
            print(f"    notes: {m['notes']}")
    return 0


def cmd_verify(entries: list[dict], ident: str | None) -> int:
    todo = [find(entries, ident)] if ident else entries
    all_ok = True
    for e in todo:
        if e["status"] == "published" and ident is None:
            print(f"{e['id']}: SKIP (status=published, no test data)")
            continue
        ok, report = verify_entry(e)
        all_ok &= ok
        print(f"{e['id']} ({e['date']}): {'OK' if ok else 'FAIL'}")
        for line in report:
            print(line)
    print("ALL OK" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


def cmd_decrypt(entries: list[dict], ident: str, mid: str) -> int:
    e = find(entries, ident)
    msgs = [m for m in e.get("messages", []) if m["id"] == mid]
    if not msgs:
        print(f"Сообщение {mid!r} не найдено в {e['id']}", file=sys.stderr)
        return 2
    m = msgs[0]
    if not m.get("cipher") or not m.get("key"):
        print("Для этого сообщения нет шифротекста/ключа в базе", file=sys.stderr)
        return 2
    machine = build_machine(e, m["key"])
    print(machine.decipher(m["cipher"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="База суточных ключей Enigma")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="список записей")
    sp = sub.add_parser("show", help="карточка ключа")
    sp.add_argument("ident", help="id или дата (YYYY-MM-DD)")
    sp = sub.add_parser("verify", help="проверить записи движком")
    sp.add_argument("--id", default=None, help="только одна запись")
    sp = sub.add_parser("decrypt", help="расшифровать сообщение из базы")
    sp.add_argument("--id", required=True)
    sp.add_argument("--msg", required=True)
    args = p.parse_args(argv)
    try:
        entries = load_db()
    except (OSError, ValueError) as ex:
        print(f"Не могу прочитать базу: {ex}", file=sys.stderr)
        return 1
    try:
        if args.cmd == "list":
            return cmd_list(entries)
        if args.cmd == "show":
            return cmd_show(entries, args.ident)
        if args.cmd == "verify":
            return cmd_verify(entries, args.id)
        if args.cmd == "decrypt":
            return cmd_decrypt(entries, args.id, args.msg)
    except (KeyError, ValueError) as ex:
        print(f"Ошибка: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
