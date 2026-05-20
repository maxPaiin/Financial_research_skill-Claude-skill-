"""
Multi-source conflict resolution — canonical per §5.3.

When multiple providers return values for the same (ticker, asof, field):

  diff_pct < 0.05  → mean, confidence = max(c1, c2)
  diff_pct < 0.20  → higher-confidence source, log dispersion warning
  else             → higher-confidence source, confidence *= 0.5,
                     log to data_provenance.json with severity="high"

Three+ sources: take median; halve confidence if max-min > 0.20 × median.

Conflict resolution thresholds are the canonical location per §5.3.
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import date
from pathlib import Path
from typing import Optional

from .base import DataPoint

log = logging.getLogger(__name__)

# Canonical thresholds
_AGREE_THRESHOLD = 0.05     # diff_pct below → treat as agreement, take mean
_WARN_THRESHOLD = 0.20      # diff_pct below → warn, take higher-confidence value
_CONFIDENCE_PENALTY = 0.5   # multiply confidence when diff_pct >= WARN_THRESHOLD

_PROVENANCE_LOG: list[dict] = []
_PROVENANCE_PATH = Path("/home/claude/work/data_provenance.json")


def resolve(points: list[DataPoint]) -> DataPoint:
    """
    Resolve a list of DataPoints for the same field into a single DataPoint.
    Logs conflicts to the provenance log.
    """
    valid = [p for p in points if p.value is not None]
    if not valid:
        return points[0] if points else DataPoint(value=None, confidence=0.0, source="none",
                                                   asof=date.today())
    if len(valid) == 1:
        return valid[0]

    values = [p.value for p in valid]

    if len(valid) == 2:
        v1, v2 = values
        denom = max(abs(v1), abs(v2), 1e-9)
        diff_pct = abs(v1 - v2) / denom

        if diff_pct < _AGREE_THRESHOLD:
            mean_val = (v1 + v2) / 2
            conf = max(p.confidence for p in valid)
            return DataPoint(
                value=round(mean_val, 6),
                confidence=conf,
                source=f"resolved:{valid[0].source}+{valid[1].source}",
                asof=valid[0].asof,
                n_sources_agreed=2,
            )
        else:
            best = max(valid, key=lambda p: p.confidence)
            severity = "high" if diff_pct >= _WARN_THRESHOLD else "warning"
            out_conf = best.confidence * (_CONFIDENCE_PENALTY if severity == "high" else 1.0)
            _log_conflict(valid, diff_pct, severity)
            return DataPoint(
                value=best.value,
                confidence=round(out_conf, 4),
                source=best.source,
                asof=best.asof,
                n_sources_agreed=1,
            )
    else:
        # 3+ sources: median
        median_val = statistics.median(values)
        max_val, min_val = max(values), min(values)
        spread = (max_val - min_val) / max(abs(median_val), 1e-9)
        conf = max(p.confidence for p in valid)
        if spread > _WARN_THRESHOLD:
            conf *= _CONFIDENCE_PENALTY
            _log_conflict(valid, spread, "high")
        best = min(valid, key=lambda p: abs(p.value - median_val))
        return DataPoint(
            value=round(median_val, 6),
            confidence=round(conf, 4),
            source=f"resolved:median({len(valid)})",
            asof=best.asof,
            n_sources_agreed=len(valid),
        )


def _log_conflict(points: list[DataPoint], diff_pct: float, severity: str):
    entry = {
        "severity": severity,
        "diff_pct": round(diff_pct, 4),
        "sources": [{"source": p.source, "value": p.value, "confidence": p.confidence}
                    for p in points],
    }
    _PROVENANCE_LOG.append(entry)
    if severity == "high":
        log.warning("High data conflict (%s%%): %s", round(diff_pct * 100, 1),
                    [p.source for p in points])


def flush_provenance():
    """Write accumulated provenance log to disk."""
    _PROVENANCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROVENANCE_PATH.write_text(
        json.dumps({"conflicts": _PROVENANCE_LOG}, indent=2),
        encoding="utf-8",
    )
