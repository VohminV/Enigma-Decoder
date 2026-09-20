#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Контракты Phase 7 (CrackerEngine/Scorer) — ТОЛЬКО интерфейсы, AUD-remediation.

Здесь нет поиска, нет n-gram моделей, нет эвристик: лишь формы данных
и границы, чтобы будущий cracker/scorer встали без переделки GUI и services.
Реализации запрещены до отдельного этапа (см. AUDIT.md Remediation).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Candidate:
    """Один кандидат криптоанализа: конфигурация + расшифровка + оценка."""
    config: dict
    plaintext: str
    score: float | None = None
    entry_id: str = ""
    message_id: str = ""
    key: str = ""
    note: str = ""

    @classmethod
    def from_historical(cls, item: dict) -> "Candidate":
        """Адаптер текущего historical lookup к контракту (чистые данные)."""
        return cls(config=item.get("config") or {},
                   plaintext=item.get("plaintext", ""),
                   score=None,
                   entry_id=item.get("entry_id", ""),
                   message_id=item.get("message_id", ""),
                   key=item.get("key", ""),
                   note="historical lookup (no scoring)")


@dataclass(frozen=True)
class SearchProgress:
    done: int
    total: int
    elapsed_s: float = 0.0


class Scorer(ABC):
    """Оценка правдоподобия расшифровки. Замена scorer не трогает cracker."""

    name: str = "base"

    @abstractmethod
    def score(self, text: str) -> float:
        """Чем выше, тем правдоподобнее. Детерминирован для одного входа."""
        raise NotImplementedError


class CrackerEngine(ABC):
    """Автоматический поиск. Streaming/top-N: миллионы кандидатов в RAM
    не хранятся — результаты отдаются через on_candidate по мере готовности."""

    @abstractmethod
    def search(self, cipher: str,
               on_candidate: Optional[Callable[[Candidate], None]] = None,
               on_progress: Optional[Callable[[SearchProgress], None]] = None,
               should_cancel: Optional[Callable[[], bool]] = None) -> list[Candidate]:
        """Вернуть top-N кандидатов. Кооперативная отмена через
        should_cancel; принудительного убийства потока нет."""
        raise NotImplementedError
