"""Persistent watchlist of tickers that the model can view and edit."""

import json
import threading
from collections.abc import Callable, Iterable
from pathlib import Path

from models import WatchlistChange

DEFAULT_TICKERS = ("GOOGL", "BABA", "CEG", "CCJ", "NOW", "NTR", "RIO", "NVDA", "MU", "META", "JPM", "XLV")


def normalize_tickers(tickers: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(ticker.strip().upper() for ticker in tickers if ticker.strip()))


class Watchlist:
    """Tickers stored as a JSON array; falls back to the defaults until first modified."""

    def __init__(self, path: Path, defaults: Iterable[str] = DEFAULT_TICKERS) -> None:
        self._path = path
        self._defaults = normalize_tickers(defaults)
        self._lock = threading.Lock()

    @property
    def tickers(self) -> list[str]:
        if not self._path.exists():
            return list(self._defaults)
        return json.loads(self._path.read_text())

    def add(self, tickers: Iterable[str], is_valid: Callable[[str], bool]) -> WatchlistChange:
        with self._lock:
            current = self.tickers
            requested = normalize_tickers(tickers)
            already_present = [ticker for ticker in requested if ticker in current]
            candidates = [ticker for ticker in requested if ticker not in current]
            invalid = [ticker for ticker in candidates if not is_valid(ticker)]
            added = [ticker for ticker in candidates if ticker not in invalid]
            updated = current + added
            if added:
                self._save(updated)
            return WatchlistChange(applied=added, skipped=already_present, invalid=invalid, watchlist=updated)

    def remove(self, tickers: Iterable[str]) -> WatchlistChange:
        with self._lock:
            current = self.tickers
            requested = normalize_tickers(tickers)
            removed = [ticker for ticker in requested if ticker in current]
            not_present = [ticker for ticker in requested if ticker not in current]
            updated = [ticker for ticker in current if ticker not in removed]
            if removed:
                self._save(updated)
            return WatchlistChange(applied=removed, skipped=not_present, invalid=[], watchlist=updated)

    def _save(self, tickers: list[str]) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(tickers, indent=2))
        temporary.replace(self._path)
