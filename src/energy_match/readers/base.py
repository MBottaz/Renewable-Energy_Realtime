"""
Abstract base for all data readers.

Every reader returns a ``TimeSeries`` (see ``models.py``).
"""

from abc import ABC, abstractmethod

from energy_match.models import TimeSeries


class Reader(ABC):
    """Protocol for reading energy data into a ``TimeSeries``."""

    @abstractmethod
    def read(self) -> TimeSeries:
        """Read and return a TimeSeries."""
        ...