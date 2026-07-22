"""Abstract base for all result writers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from energy_match.models import MatchResult


class Writer(ABC):
    """Abstract base for all result writers."""

    @abstractmethod
    def write(self, result: MatchResult, target: str | Path) -> None:
        """Write the match result to *target*."""
        ...