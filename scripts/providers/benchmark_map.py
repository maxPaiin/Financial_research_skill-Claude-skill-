"""
Benchmark -> proxy ETF (v0.4 B3).

A fund's vote on a stock depends on whether it holds the stock above its
benchmark weight (DEC-1). Benchmark constituents are not free data, so the
benchmark is approximated by an ETF that tracks it (or a near relative), whose
top-10 weights yfinance can read. This table maps the benchmark name *as
printed on the factsheet* to that proxy and says how good the approximation is.

Rules:
- Sector-specific patterns are checked before broad ones, so "S&P 500
  Information Technology" maps to XLK, never to SPY.
- A broad pattern applies only to a broad index: a benchmark that also names a
  sector it has no row for ("MSCI World Health Care"), or a variant the proxy
  does not track ("MSCI World Growth", "MSCI ACWI ex USA", "S&P 500 Equal
  Weight"), is unmapped rather than given a plausible-looking proxy.
- An unmapped benchmark returns None and the fund casts presence votes.
- Keep the table small and reviewable. Add a row only for a benchmark seen on a
  real factsheet.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

APPROXIMATE = "approximate"
EXACT = "exact"

# (substrings, proxy ETF, quality, note) — first match wins.
_SECTOR_ROWS: list[tuple[tuple[str, ...], str, str, str]] = [
    (("s&p 500 information technology", "technology select sector"),
     "XLK", APPROXIMATE, "capped index"),
    (("msci acwi information technology", "msci ac world information technology",
      "msci world information technology"),
     "IXN", APPROXIMATE, "tracks S&P Global 1200 IT"),
    (("msci usa imi information technology",),
     "VGT", APPROXIMATE, "MSCI US IMI IT 25/50"),
]
_BROAD_ROWS: list[tuple[tuple[str, ...], str, str, str]] = [
    (("nasdaq-100", "nasdaq 100"), "QQQ", EXACT, ""),
    (("russell 1000 growth",), "IWF", EXACT, ""),
    (("russell 1000",), "IWB", EXACT, ""),
    (("s&p 500",), "SPY", EXACT, ""),
    # "msci ac world" is the spelling the IXN row already uses; factsheets
    # print "MSCI AC World Index" as often as "MSCI ACWI".
    (("msci acwi", "msci all country world", "msci ac world"), "ACWI", EXACT, ""),
    (("msci world",), "URTH", EXACT, ""),
]

_SECTOR_WORDS = re.compile(
    r"information technology|\btechnology\b|\btech\b|health|financial|\benergy\b|"
    r"consumer|industrial|material|utilit|real estate|communication|semiconductor|"
    r"telecom|biotech|pharma|\bbank|\breit")
_VARIANT_WORDS = re.compile(
    r"\b(?:growth|value|small|mid|large|quality|momentum|dividend|yield|esg|sri|"
    r"islamic|equal|minimum|min vol|ex)\b")
_DASHES = re.compile(r"[‐-―−]")


def normalize_benchmark(raw: Optional[str]) -> str:
    """Casefolded benchmark text with one kind of dash and single spaces."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", str(raw)).replace("&amp;", "&")
    s = _DASHES.sub("-", s).casefold()
    return " ".join(s.split())


def proxy_for(raw: Optional[str]) -> Optional[tuple[str, str]]:
    """(proxy ETF, quality) for a benchmark as printed, or None when unmapped.

    quality is "exact" (the ETF tracks the benchmark) or "approximate (...)".
    """
    text = normalize_benchmark(raw)
    if not text:
        return None
    for patterns, etf, quality, note in _SECTOR_ROWS:
        if any(p in text for p in patterns):
            return etf, f"{quality} ({note})" if note else quality
    if _SECTOR_WORDS.search(text):
        return None
    for patterns, etf, quality, note in _BROAD_ROWS:
        for p in patterns:
            if p in text:
                rest = text.replace(p, " ")
                if _VARIANT_WORDS.search(rest):
                    break            # a variant this proxy does not track
                return etf, quality
    return None
