"""
PDF snapshot provider — fund holdings at a given asof date.

Reads the structured JSON from Stage 1 extraction and exposes holdings
data as a provider. Used for single-snapshot vs multi-snapshot mode tracking.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from .base import DEFAULT_CONFIDENCE, DataPoint, FundamentalsProvider, FundamentalsRecord

log = logging.getLogger(__name__)


class PDFSnapshotProvider(FundamentalsProvider):
    """Reads fund holdings from the Stage 1 extraction JSON."""

    def __init__(self, holdings_path: Path):
        self._path = holdings_path
        self._data: Optional[dict] = None
        self._snapshot_index: dict[str, list[dict]] = {}  # ticker → [{fund_id, asof, weight}]
        self._loaded = False

    @property
    def name(self) -> str:
        return "pdf"

    @property
    def base_confidence(self) -> float:
        return DEFAULT_CONFIDENCE["pdf"]

    def _ensure_loaded(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("PDFSnapshotProvider: cannot load %s: %s", self._path, e)
            return

        for fund in self._data.get("funds", []):
            fid = fund.get("fund_id")
            asof_str = fund.get("asof") or fund.get("reporting_date", "")
            for h in fund.get("holdings", []):
                tkr = h.get("ticker_normalized") or h.get("ticker", "")
                if not tkr:
                    continue
                self._snapshot_index.setdefault(tkr, []).append({
                    "fund_id": fid,
                    "asof": asof_str,
                    "weight": h.get("weight", 0.0),
                })

    def supports(self, ticker: str) -> bool:
        self._ensure_loaded()
        return ticker in self._snapshot_index

    def fetch(self, ticker: str, asof: date) -> Optional[FundamentalsRecord]:
        self._ensure_loaded()
        snapshots = self._snapshot_index.get(ticker, [])
        if not snapshots:
            return None

        n_snapshots = len(snapshots)
        conf = DEFAULT_CONFIDENCE["pdf_multi"] if n_snapshots > 1 else DEFAULT_CONFIDENCE["pdf"]
        source_tag = f"pdf:{'multi' if n_snapshots > 1 else 'single'}"

        return FundamentalsRecord(
            ticker=ticker,
            asof=asof,
            is_adr=False,  # unknown from PDF alone
        )

    def get_snapshot_mode(self, ticker: str) -> dict:
        """Return snapshot availability info for a ticker."""
        self._ensure_loaded()
        snapshots = self._snapshot_index.get(ticker, [])
        return {
            "n_snapshots": len(snapshots),
            "mode": "multi_snapshot" if len(snapshots) > 1 else "single_snapshot",
            "confidence": (
                DEFAULT_CONFIDENCE["pdf_multi"] if len(snapshots) > 1
                else DEFAULT_CONFIDENCE["pdf"]
            ),
            "snapshots": snapshots,
        }
