"""
yfinance provider — degraded-PIT fallback (refactored from v1 fetch_market_data.py).

Confidence baseline: 0.5 (current values projected back, not true PIT).
This is the only file that imports yfinance — canonical per §8.1 acceptance criteria.

v0.31 (E2.3) adds `fetch_close_series()` — daily closes for the coherence
overlay's ETF relative-strength check. It lives here for the same reason the
fundamentals fetch does: yfinance is imported in exactly one file. The
relative-strength arithmetic itself is in `etf_relative_strength.py` so it
stays unit-testable offline.

v0.34 (A3):
- Symbols: the pipeline's canonical share-class form is `BRK.B`; Yahoo writes
  `BRK-B`. `to_yahoo_symbol()` maps on the way out and results stay keyed by
  the canonical ticker.
- ROE and net income are real annual series from `Ticker.income_stmt` and
  `Ticker.balance_sheet` (usually four fiscal years). v0.33 repeated the
  trailing value five times, so the multi-year screen rules saw one number
  (F8). With no statements, the series is ONE trailing-twelve-month point —
  never repeated.
- Negative or zero equity leaves that year's ROE undefined, and D/E is
  undefined whenever the latest equity is <= 0 (F10, same guard as EDGAR).
- `fetch_etf_top_holdings()` (benchmark proxy weights, B3) and
  `fetch_close_series_dated()` (dated closes, D2).
- Replay: when YF_REPLAY_DIR is set, every call reads recorded JSON
  (`<dir>/<Yahoo symbol>.json`) instead of the network. All tests use it.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

try:  # Imported here and nowhere else (I11). Optional so replay runs need no network stack.
    import yfinance as yf
except ImportError:  # pragma: no cover - exercised only without the dependency
    yf = None

from .base import DataPoint, FundamentalsRecord, FundamentalsProvider, DEFAULT_CONFIDENCE
from .industry_map import normalize as normalize_industry

log = logging.getLogger(__name__)

REPLAY_ENV = "YF_REPLAY_DIR"

# Matches the country variants yfinance returns for US domiciles. The earlier
# implementation hard-listed ("UNITED STATES", "US", "") and missed common
# values like "USA" or "United States of America" — which then flagged
# obviously-domestic stocks as ADRs.
_US_COUNTRY_RE = re.compile(
    r"^(?:US|USA|U\.S\.|U\.S\.A\.|UNITED\s+STATES(?:\s+OF\s+AMERICA)?)$",
    re.IGNORECASE,
)

# Yahoo exchange suffixes: a dot before one of these is part of a non-US
# symbol (2330.TW), not a US share class, and is left alone.
_YAHOO_EXCHANGE_SUFFIXES = {
    "T", "HK", "TW", "TWO", "L", "SS", "SZ", "PA", "DE", "AS", "MI", "MC", "TO",
    "AX", "KS", "KQ", "SI", "BK", "SW", "CO", "ST", "HE", "OL", "BR", "LS", "VI",
    "IR", "NZ", "SA", "MX", "JK", "NS", "BO", "KL", "V", "NE", "F",
}
_US_CLASS_RE = re.compile(r"^([A-Z]{1,5})[.-]([A-Z]{1,2})$")

_N_YEARS = 5
_NET_INCOME_ROWS = ("Net Income", "Net Income Common Stockholders")
_EQUITY_ROWS = ("Stockholders Equity", "Common Stock Equity")


def _is_us_country(raw: Optional[str]) -> bool:
    if not raw:
        return False
    return bool(_US_COUNTRY_RE.match(raw.strip()))


def to_yahoo_symbol(ticker: str) -> str:
    """Canonical ticker -> Yahoo symbol: BRK.B -> BRK-B, BF.B -> BF-B."""
    t = (ticker or "").strip().upper()
    m = _US_CLASS_RE.match(t)
    if m and m.group(2) not in _YAHOO_EXCHANGE_SUFFIXES:
        return f"{m.group(1)}-{m.group(2)}"
    return t


def from_yahoo_symbol(symbol: str) -> str:
    """Yahoo symbol -> canonical ticker: BRK-B -> BRK.B (others unchanged)."""
    s = (symbol or "").strip().upper()
    m = _US_CLASS_RE.match(s)
    if m and "-" in s:
        return f"{m.group(1)}.{m.group(2)}"
    return s


def _number(value) -> Optional[float]:
    """A finite float, or None (yfinance frames carry NaN for missing cells)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# --- Data sources: the network, or recorded JSON ----------------------------

class _LiveSource:
    """yfinance over the network. Frames are reduced to plain dicts here so the
    provider logic below is the same for live and replayed data."""

    @staticmethod
    def _ticker(symbol: str):
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        return yf.Ticker(symbol)

    def info(self, symbol: str) -> dict:
        return self._ticker(symbol).info or {}

    @staticmethod
    def _periods(frame) -> dict[str, dict[str, Optional[float]]]:
        if frame is None or getattr(frame, "empty", True):
            return {}
        out: dict[str, dict[str, Optional[float]]] = {}
        for col in frame.columns:
            try:
                iso = col.date().isoformat()
            except AttributeError:
                iso = str(col)[:10]
            out[iso] = {str(row): _number(frame.at[row, col]) for row in frame.index}
        return out

    def statements(self, symbol: str) -> tuple[dict, dict]:
        t = self._ticker(symbol)
        return self._periods(t.income_stmt), self._periods(t.balance_sheet)

    def top_holdings(self, symbol: str) -> dict[str, float]:
        frame = self._ticker(symbol).funds_data.top_holdings
        if frame is None or getattr(frame, "empty", True):
            return {}
        col = "Holding Percent" if "Holding Percent" in frame.columns else frame.columns[-1]
        return {str(sym): _number(frame.at[sym, col]) for sym in frame.index}

    def closes(self, symbol: str, start: Optional[date] = None, end: Optional[date] = None,
               period: Optional[str] = None) -> list[tuple[date, float]]:
        t = self._ticker(symbol)
        if start is not None:
            # yfinance treats `end` as exclusive; one extra day keeps it inclusive.
            hist = t.history(start=start.isoformat(),
                             end=((end or date.today()) + timedelta(days=1)).isoformat(),
                             auto_adjust=True)
        else:
            hist = t.history(period=period or "2y", auto_adjust=True)
        out = []
        for ts, value in hist["Close"].items():
            v = _number(value)
            if v is not None and v > 0:
                out.append((ts.date(), v))
        return out


class _ReplaySource:
    """Recorded JSON per Yahoo symbol:

    {"info": {...},
     "income_stmt":   {"2025-12-31": {"Net Income": 1.0e9, ...}, ...},
     "balance_sheet": {"2025-12-31": {"Stockholders Equity": 9.0e9, ...}, ...},
     "top_holdings":  {"AAPL": 0.12, ...},
     "history":       [["2026-01-02", 123.4], ...]}

    A symbol without a file behaves like a symbol Yahoo does not know.
    """

    def __init__(self, root: Path):
        self.root = root

    def _load(self, symbol: str) -> dict:
        path = self.root / f"{symbol}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def info(self, symbol: str) -> dict:
        return self._load(symbol).get("info") or {}

    def statements(self, symbol: str) -> tuple[dict, dict]:
        data = self._load(symbol)
        return data.get("income_stmt") or {}, data.get("balance_sheet") or {}

    def top_holdings(self, symbol: str) -> dict[str, float]:
        return dict(self._load(symbol).get("top_holdings") or {})

    def closes(self, symbol: str, start: Optional[date] = None, end: Optional[date] = None,
               period: Optional[str] = None) -> list[tuple[date, float]]:
        out = []
        for iso, value in self._load(symbol).get("history") or []:
            d = date.fromisoformat(iso)
            if (start is None or d >= start) and (end is None or d <= end):
                v = _number(value)
                if v is not None and v > 0:
                    out.append((d, v))
        return sorted(out)


def _source():
    root = os.environ.get(REPLAY_ENV)
    return _ReplaySource(Path(root)) if root else _LiveSource()


# --- Market data helpers ------------------------------------------------------

def fetch_close_series(
    symbols: list[str],
    period: str = "2y",
) -> dict[str, list[float]]:
    """Daily closes per symbol, oldest → newest (v0.31 E2.3).

    Returns only symbols that yielded a usable series; a symbol that fails or
    comes back empty is simply absent, and the caller records it as
    "insufficient data" rather than substituting a proxy. Each symbol is
    fetched independently so one bad ticker cannot void the whole batch.
    Results are keyed by the symbol as passed in.
    """
    src = _source()
    out: dict[str, list[float]] = {}
    for sym in dict.fromkeys(s for s in symbols if s):
        try:
            closes = [v for _, v in src.closes(to_yahoo_symbol(sym), period=period)]
        except Exception as e:  # noqa: BLE001 — one bad symbol must not abort the batch
            log.warning("yfinance close-series fetch failed for %s: %s", sym, e)
            continue
        if closes:
            out[sym] = closes
    return out


def fetch_close_series_dated(
    symbols: list[str],
    start: date,
    end: date,
) -> dict[str, list[tuple[date, float]]]:
    """Dated daily closes per symbol between start and end inclusive (v0.4 D2).

    Keyed by the symbol as passed in; a symbol without data is absent.
    """
    src = _source()
    out: dict[str, list[tuple[date, float]]] = {}
    for sym in dict.fromkeys(s for s in symbols if s):
        try:
            series = src.closes(to_yahoo_symbol(sym), start=start, end=end)
        except Exception as e:  # noqa: BLE001
            log.warning("yfinance dated close fetch failed for %s: %s", sym, e)
            continue
        if series:
            out[sym] = series
    return out


def fetch_etf_top_holdings(symbols: list[str]) -> dict[str, dict[str, float]]:
    """{etf: {canonical ticker: weight}} from Yahoo's fund top holdings (v0.4 B3).

    Weights are fractions of the fund (0.12 = 12%). An ETF that fails or
    returns nothing is absent — the caller records why.
    """
    src = _source()
    out: dict[str, dict[str, float]] = {}
    for etf in dict.fromkeys(s for s in symbols if s):
        try:
            raw = src.top_holdings(to_yahoo_symbol(etf))
        except Exception as e:  # noqa: BLE001
            log.warning("yfinance top-holdings fetch failed for %s: %s", etf, e)
            continue
        holdings = {from_yahoo_symbol(sym): w for sym, w in raw.items()
                    if sym and w is not None and w > 0}
        if holdings:
            out[etf] = holdings
    return out


# --- Annual statements -> ROE and net-income series --------------------------

def annual_rows(
    income: dict[str, dict], balance: dict[str, dict], asof: date,
) -> list[tuple[date, float, Optional[float]]]:
    """[(fiscal year end, net income, equity)], oldest first, at most five.

    Net income is `Net Income`, else `Net Income Common Stockholders`; equity is
    `Stockholders Equity`, else `Common Stock Equity` — both from the same
    period's statements. Periods after asof are ignored.
    """
    rows = []
    for iso in sorted(income):
        try:
            end = date.fromisoformat(iso[:10])
        except ValueError:
            continue
        if end > asof:
            continue
        ni = next((_number(income[iso].get(k)) for k in _NET_INCOME_ROWS
                   if _number(income[iso].get(k)) is not None), None)
        if ni is None:
            continue
        sheet = balance.get(iso) or {}
        eq = next((_number(sheet.get(k)) for k in _EQUITY_ROWS
                   if _number(sheet.get(k)) is not None), None)
        rows.append((end, ni, eq))
    return rows[-_N_YEARS:]


class yfinanceProvider(FundamentalsProvider):
    """Fetches fundamentals and market data from yfinance with degraded PIT confidence."""

    @property
    def name(self) -> str:
        return "yfinance"

    @property
    def base_confidence(self) -> float:
        return DEFAULT_CONFIDENCE["yfinance"]

    def supports(self, ticker: str) -> bool:
        try:
            return bool(_source().info(to_yahoo_symbol(ticker)).get("symbol"))
        except Exception:
            return False

    def fetch(self, ticker: str, asof: date) -> Optional[FundamentalsRecord]:
        try:
            src = _source()
            symbol = to_yahoo_symbol(ticker)
            info = src.info(symbol) or {}
            if not info.get("symbol"):
                return None
            conf = self.base_confidence
            try:
                income, balance = src.statements(symbol)
            except Exception as e:  # noqa: BLE001 — statements are optional
                log.warning("yfinance statements failed for %s: %s", ticker, e)
                income, balance = {}, {}

            # ROE / net income: real annual series, else ONE trailing point.
            roe_5y: list[Optional[DataPoint]] = []
            ni_5y: list[Optional[DataPoint]] = []
            undefined_years: list[int] = []
            rows = annual_rows(income, balance, asof)
            latest_equity: Optional[float] = None
            if rows:
                for end, ni, eq in rows:
                    tag = f"yfinance:annual-{end.isoformat()}"
                    ni_5y.append(DataPoint(value=ni, confidence=conf, source=tag, asof=asof))
                    if eq is not None and eq <= 0:
                        undefined_years.append(end.year)   # F10: never sign-flipped
                        eq = None
                    roe_5y.append(
                        DataPoint(value=round(ni / eq, 4), confidence=conf, source=tag, asof=asof)
                        if eq is not None else
                        DataPoint(value=None, confidence=0.0, source=tag, asof=asof))
                equities = [eq for _, _, eq in rows if eq is not None]
                latest_equity = rows[-1][2] if rows[-1][2] is not None else (
                    equities[-1] if equities else None)
                data_asof = rows[-1][0]
            else:
                tag = f"yfinance:ttm-{asof.strftime('%Y-%m')}"
                book = _number(info.get("bookValue"))
                roe_val = _number(info.get("returnOnEquity"))
                if book is not None and book <= 0:
                    roe_val = None                          # negative book: undefined
                if roe_val is not None:
                    roe_5y = [DataPoint(value=round(roe_val, 4), confidence=conf,
                                        source=tag, asof=asof)]
                ni_val = _number(info.get("netIncomeToCommon"))
                if ni_val is not None:
                    ni_5y = [DataPoint(value=ni_val, confidence=conf, source=tag, asof=asof)]
                latest_equity = book
                data_asof = date.today()

            source_tag = f"yfinance:{asof.strftime('%Y-%m')}"

            # EV/EBITDA
            ev_ebitda_val = _number(info.get("enterpriseToEbitda"))
            ev_ebitda = DataPoint(value=round(ev_ebitda_val, 4), confidence=conf,
                                  source=source_tag, asof=asof) \
                if ev_ebitda_val is not None else None

            # Debt/Equity — yfinance reports it as a percentage. Undefined when
            # the latest equity is <= 0, so a negative ratio can never pass the
            # screen's ceiling.
            de_val = _number(info.get("debtToEquity"))
            if de_val is not None:
                de_val = de_val / 100.0
            if de_val is not None and (de_val < 0 or (latest_equity is not None
                                                      and latest_equity <= 0)):
                de_val = None
            debt_equity = DataPoint(value=round(de_val, 4), confidence=conf,
                                    source=source_tag, asof=asof) \
                if de_val is not None else None

            # Industry
            raw_sector = info.get("sector") or info.get("industry")
            industry = normalize_industry(raw_sector)

            # Market cap and ADV
            mkt_cap = info.get("marketCap")
            market_cap = DataPoint(value=mkt_cap, confidence=conf, source=source_tag, asof=asof) \
                if mkt_cap else None

            adv_val = info.get("averageDailyVolume10Day") or info.get("averageVolume10days")
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            adv_usd = (adv_val * price) if (adv_val and price) else None
            adv = DataPoint(value=adv_usd, confidence=conf, source=source_tag, asof=asof) \
                if adv_usd else None

            # ADR detection: a US-listed ticker whose company domicile is
            # not the US. If yfinance returns no country at all, we
            # conservatively treat it as not-ADR (extraction already filtered
            # to US-listed equities, so the listing side is implied).
            country = info.get("country")
            is_adr = bool(country) and not _is_us_country(country)

            return FundamentalsRecord(
                ticker=ticker,              # keyed by the canonical ticker, not Yahoo's
                asof=asof,
                roe_5y=roe_5y,
                ev_ebitda=ev_ebitda,
                debt_equity=debt_equity,
                net_income_5y=ni_5y,
                industry=industry,
                market_cap=market_cap,
                adv=adv,
                is_adr=is_adr,
                # The latest fiscal year end of the statements used; a trailing
                # snapshot is as of today. If EDGAR also contributed, the
                # registry keeps EDGAR's data_asof (see registry.fetch()).
                data_asof=data_asof,
                roe_undefined_years=undefined_years,
                reporting_currency=info.get("financialCurrency"),
            )
        except Exception as e:
            log.warning("yfinance fetch failed for %s: %s", ticker, e)
            return None
