"""
EDGAR provider — true point-in-time US fundamentals via SEC EDGAR.

Contract (canonical per §5.3):
- User-Agent: "FinancialResearchSkill-v0.3 <contact-email>" (B1, v0.3)
    SEC requires every EDGAR request to declare a User-Agent that identifies the
    application AND provides a contact email; requests lacking a contact email
    (or using a generic bot-like UA) are answered with 403 Forbidden. The email
    is supplied by the user and gated at Stage 0 (validate_uploads.py); it is
    injected here via the `contact_email=` kwarg or the EDGAR_CONTACT_EMAIL env
    var — never hardcoded. The email is placed ONLY into this request header
    (SEC's stated use: to contact the operator if the script causes problems);
    it is not stored and not transmitted anywhere else.
- Throttle: minimum 100 ms between requests (<= 10 req/s, SEC fair access).
    SEC publishes a request-RATE limit, not a daily cap (v0.34 F13), so there
    is no daily budget. A 10,000-request runaway guard stops a looping run and
    logs a WARNING.
- Ticker map (v0.34 A2): www.sec.gov/files/company_tickers_exchange.json
    (ticker -> CIK, issuer name, listing exchange), parsed by field name and
    cached under `ticker_exchange_map`; refreshed when the cache is older than
    7 days (an operational TTL with no effect on scores). `data.sec.gov` serves
    only the companyfacts and submissions endpoints.
- Cache: companyfacts and submissions by CIK.
- Filers: 10-K (domestic) and 20-F / 40-F (foreign private issuers). Facts are
    read from `us-gaap` first, then `ifrs-full`.
- Units: a ratio (ROE, D/E) is built only from a numerator and denominator in
    the SAME unit for the SAME period end. Ratios are dimensionless, so a filer
    reporting in TWD or EUR needs no conversion — and none exists here.
- Retry on HTTP 429: exponential 1s → 2s → 4s, then fall through to yfinance.
- Offline mode (`offline=True` or EDGAR_OFFLINE=1): cache only, never the
    network — used by fixture tests and replayed runs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests

from .base import DataPoint, FundamentalsRecord, FundamentalsProvider, DEFAULT_CONFIDENCE
from .industry_map import normalize as normalize_industry
from .names import normalize_company_name

log = logging.getLogger(__name__)

# Canonical constants — do not duplicate elsewhere.
# B1 (v0.3): the UA is built per-instance and MUST carry a contact email.
_USER_AGENT_APP = "FinancialResearchSkill-v0.3"
_MIN_INTERVAL_S = 0.10                  # 100 ms between requests
_RUNAWAY_REQUEST_GUARD = 10_000         # not a quota: stops a looping run
_RETRY_DELAYS = [1.0, 2.0, 4.0]
_EDGAR_BASE = "https://data.sec.gov"
_COMPANY_FACTS_URL = _EDGAR_BASE + "/api/xbrl/companyfacts/CIK{cik:010d}.json"
_SUBMISSIONS_URL = _EDGAR_BASE + "/submissions/CIK{cik:010d}.json"
_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_TICKER_MAP_CACHE_KEY = "ticker_exchange_map"   # new key: a v0.33 cache is never reused
_TICKER_MAP_TTL_S = 7 * 24 * 3600

# The default cache comes from paths.cache_dir() (v0.4 C1): EDGAR_CACHE_DIR when
# set, the work dir in the claude.ai sandbox (the skill dir may be read-only
# there), <repo-root>/.cache/edgar elsewhere. The `cache_dir=` kwarg overrides.


def _default_cache_dir() -> Path:
    from paths import cache_dir   # scripts/ is on sys.path wherever providers is
    return cache_dir()

# Annual reports by filer type; 10-Q adds interim balance sheets for D/E.
ANNUAL_FORMS = ("10-K", "20-F", "40-F")
FOREIGN_PRIVATE_ISSUER_FORMS = ("20-F", "40-F")
_BALANCE_SHEET_FORMS = ANNUAL_FORMS + ("10-Q",)

# v0.34 A2: taxonomies in reading order, and per item the candidate concepts
# (the first one with data in the window wins). Debt has a us-gaap special
# case — see `_debt_series`.
TAXONOMIES = ("us-gaap", "ifrs-full")
CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "net_income": {
        "us-gaap": ("NetIncomeLoss", "ProfitLoss"),
        "ifrs-full": ("ProfitLossAttributableToOwnersOfParent", "ProfitLoss"),
    },
    "equity": {
        "us-gaap": (
            "StockholdersEquity",
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        ),
        "ifrs-full": ("EquityAttributableToOwnersOfParent", "Equity"),
    },
    "debt": {
        "us-gaap": ("LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent"),
        # NoncurrentPortionOfNoncurrentBorrowings was a spec candidate; it
        # occurred in none of 19 recorded filers (A2.3 census) and was dropped.
        "ifrs-full": ("LongtermBorrowings", "Borrowings"),
    },
}

_ISO4217_RE = re.compile(r"^[A-Z]{3}$")
_N_YEARS = 5
# A duration fact counts as a fiscal year only when it spans roughly one year,
# so a fourth-quarter figure sharing the year-end date can never stand in for it.
_ANNUAL_MIN_DAYS, _ANNUAL_MAX_DAYS = 300, 400
# Issuers change tags over time (NetIncomeLoss -> ProfitLoss, LongTermDebt ->
# LongTermDebtNoncurrent). A candidate counts as current when its latest period
# ends within two years of asof; a stale tag never beats a current one.
_CURRENT_WITHIN_DAYS = 730
# D/E pairs debt with equity at one balance-sheet date, no older than this
# before the latest equity figure.
_DE_MAX_GAP_DAYS = 400


def _resolve_contact_email(contact_email: Optional[str]) -> Optional[str]:
    """Resolve the SEC contact email: explicit kwarg > EDGAR_CONTACT_EMAIL env."""
    email = (contact_email or os.environ.get("EDGAR_CONTACT_EMAIL") or "").strip()
    return email or None


def canonical_ticker(ticker: str) -> str:
    """Internal ticker form: upper case, share class after a dot (BRK.B).

    SEC writes share classes with a hyphen (BRK-B) and some feeds with a dot;
    both map to one key, so a lookup succeeds whichever form was written.
    """
    return (ticker or "").strip().upper().replace("-", ".")


@dataclass(frozen=True)
class TickerRow:
    """One row of SEC's company_tickers_exchange.json."""
    cik: int
    name: str
    ticker: str             # canonical form (BRK.B)
    exchange: Optional[str]  # "Nasdaq" | "NYSE" | "CBOE" | "OTC" | None


def parse_exchange_file(data: Optional[dict]) -> list[TickerRow]:
    """Rows of company_tickers_exchange.json, located by field name.

    The file is `{"fields": [...], "data": [[cik, name, ticker, exchange], ...]}`;
    columns are found by name, never by position, so a reordered file still parses.
    """
    if not isinstance(data, dict):
        return []
    fields = [str(f).strip().lower() for f in data.get("fields") or []]
    if "cik" not in fields or "ticker" not in fields:
        return []
    i_cik, i_tkr = fields.index("cik"), fields.index("ticker")
    i_name = fields.index("name") if "name" in fields else None
    i_exch = fields.index("exchange") if "exchange" in fields else None
    rows: list[TickerRow] = []
    for raw in data.get("data") or []:
        try:
            cik = int(raw[i_cik])
            ticker = canonical_ticker(str(raw[i_tkr] or ""))
        except (TypeError, ValueError, IndexError):
            continue
        if not ticker:
            continue
        name = str(raw[i_name] or "") if i_name is not None and i_name < len(raw) else ""
        exch = raw[i_exch] if i_exch is not None and i_exch < len(raw) else None
        rows.append(TickerRow(cik=cik, name=name, ticker=ticker,
                              exchange=str(exch) if exch else None))
    return rows


# --- XBRL fact helpers (pure functions over a companyfacts document) ---------

def _units(facts: dict, taxonomy: str, concept: str) -> dict[str, list[dict]]:
    node = (facts.get("facts") or {}).get(taxonomy, {}).get(concept) or {}
    return node.get("units") or {}


def _currency_units(units: dict) -> list[str]:
    return sorted(u for u in units if _ISO4217_RE.match(u))


def _period_values(
    items: list[dict], asof: date, forms: tuple[str, ...], annual_duration: bool,
) -> dict[date, float]:
    """period end -> value, for facts from `forms` ending (and filed) by `asof`.

    With `annual_duration`, a fact carrying a `start` must span about one year.
    Several filings can report the same period (a later 10-K repeats prior
    years); the earliest-filed value — the figure as first reported — wins.
    """
    best: dict[date, tuple[str, float]] = {}
    for item in items:
        if item.get("form") not in forms or item.get("val") is None or not item.get("end"):
            continue
        try:
            end = date.fromisoformat(item["end"])
        except (TypeError, ValueError):
            continue
        if end > asof:
            continue
        filed = item.get("filed") or ""
        if filed:
            try:
                if date.fromisoformat(filed) > asof:
                    continue
            except ValueError:
                pass
        if annual_duration and item.get("start"):
            try:
                days = (end - date.fromisoformat(item["start"])).days
            except ValueError:
                continue
            if not _ANNUAL_MIN_DAYS <= days <= _ANNUAL_MAX_DAYS:
                continue
        prev = best.get(end)
        key = filed or "9999-99-99"
        if prev is None or key < prev[0]:
            best[end] = (key, float(item["val"]))
    return {end: val for end, (_, val) in best.items()}


class UnitSeries(dict):
    """{currency unit: {period end: value}}, plus `n_facts` — how many raw
    facts each unit carries across all of the issuer's filings."""

    def __init__(self, data=None, n_facts: Optional[dict[str, int]] = None):
        super().__init__(data or {})
        self.n_facts: dict[str, int] = dict(n_facts or {})


def _series_by_unit(
    facts: dict, taxonomy: str, concept: str, asof: date,
    forms: tuple[str, ...], annual_duration: bool,
) -> UnitSeries:
    """{currency unit: {period end: value}} for one concept; empty units dropped."""
    out = UnitSeries()
    units = _units(facts, taxonomy, concept)
    for unit in _currency_units(units):
        values = _period_values(units[unit], asof, forms, annual_duration)
        if values:
            out[unit] = values
            out.n_facts[unit] = len(units[unit])
    return out


def pick_unit(*series: dict[str, dict[date, float]]) -> Optional[str]:
    """One currency unit shared by every series, or None.

    The shared unit carrying the most facts wins — that is the reporting
    currency. Recorded filings show why "USD whenever present" is wrong: a
    20-F filer such as TSMC also tags a USD convenience translation of each
    year's figures (9 facts against 25 in TWD), and SAP carries a single USD
    fact against 41 in EUR, which left it one year of ROE. USD breaks ties,
    then the alphabet. One unit serves every series, so units never mix.
    """
    if not series or any(not s for s in series):
        return None
    shared = set(series[0])
    for s in series[1:]:
        shared &= set(s)
    if not shared:
        return None

    def weight(unit: str) -> int:
        return min(getattr(s, "n_facts", {}).get(unit, len(s[unit])) for s in series)

    return min(shared, key=lambda u: (-weight(u), u != "USD", u))


def _prefer_current(
    found: list[tuple[str, dict[str, dict[date, float]]]], asof: date,
) -> tuple[Optional[str], dict[str, dict[date, float]]]:
    """First (concept, series) whose latest period is current, else the first."""
    if not found:
        return None, {}
    horizon = asof - timedelta(days=_CURRENT_WITHIN_DAYS)
    for concept, series in found:
        latest = max(max(values) for values in series.values())
        if latest >= horizon:
            return concept, series
    return found[0]


class EDGARProvider(FundamentalsProvider):
    """Fetches fundamentals from SEC EDGAR with caching and throttling."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        contact_email: Optional[str] = None,
        offline: Optional[bool] = None,
    ):
        self._cache = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        self._cache.mkdir(parents=True, exist_ok=True)
        self._rows_by_ticker: Optional[dict[str, TickerRow]] = None
        self._name_index: Optional[dict[str, list[tuple[int, str, Optional[str]]]]] = None
        self._filing_types: dict[int, str] = {}
        self._last_request_ts: float = 0.0
        self._request_count: int = 0
        self._guard_warned = False
        self._offline = (bool(os.environ.get("EDGAR_OFFLINE"))
                         if offline is None else bool(offline))
        self._contact_email = _resolve_contact_email(contact_email)
        # SEC returns 403 without a contact email. We do not hard-fail in the
        # constructor (the Stage 0 gate is the user-facing guard), but we warn
        # loudly so a misconfigured run is diagnosable.
        if not self._contact_email and not self._offline:
            log.warning(
                "EDGAR contact email missing — SEC will likely return 403. "
                "Pass contact_email= or set EDGAR_CONTACT_EMAIL."
            )
        self._user_agent = (
            f"{_USER_AGENT_APP} {self._contact_email}"
            if self._contact_email else _USER_AGENT_APP
        )
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._user_agent})

    @property
    def name(self) -> str:
        return "edgar"

    @property
    def base_confidence(self) -> float:
        return DEFAULT_CONFIDENCE["edgar"]

    def supports(self, ticker: str) -> bool:
        try:
            return self._resolve_cik(ticker) is not None
        except Exception:
            return False

    def fetch(self, ticker: str, asof: date) -> Optional[FundamentalsRecord]:
        try:
            cik = self._resolve_cik(ticker)
            if cik is None:
                return None
            filing_type = self._detect_filing_type(cik)
            facts = self._get_company_facts(cik)
            if facts is None:
                return None
            # None when the filing carries no usable facts, so the registry
            # falls back to yfinance instead of keeping an all-empty record.
            return self._build_record(ticker, cik, asof, facts, filing_type)
        except Exception as e:
            log.warning("EDGAR fetch failed for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Ticker map lookups (A2 → A6)
    # ------------------------------------------------------------------

    def lookup_ticker(self, ticker: str) -> Optional[TickerRow]:
        """The SEC row for a ticker in either share-class form, or None."""
        self._load_ticker_map()
        return (self._rows_by_ticker or {}).get(canonical_ticker(ticker))

    def listing_exchange(self, ticker: str) -> Optional[str]:
        """"Nasdaq" / "NYSE" / "CBOE" / "OTC", or None (no exchange, or unknown)."""
        row = self.lookup_ticker(ticker)
        return row.exchange if row else None

    def name_index(self) -> dict[str, list[tuple[int, str, Optional[str]]]]:
        """Normalised issuer name -> [(cik, ticker, exchange), ...] (A6)."""
        self._load_ticker_map()
        if self._name_index is None:
            index: dict[str, list[tuple[int, str, Optional[str]]]] = {}
            for row in (self._rows_by_ticker or {}).values():
                key = normalize_company_name(row.name)
                if key:
                    index.setdefault(key, []).append((row.cik, row.ticker, row.exchange))
            for key in index:
                index[key].sort(key=lambda t: (t[1], t[0]))
            self._name_index = index
        return self._name_index

    def is_foreign_private_issuer(self, cik: int) -> bool:
        """True when the issuer's annual report is a 20-F or 40-F (A2.2)."""
        return self._detect_filing_type(cik) in FOREIGN_PRIVATE_ISSUER_FORMS

    def annual_form(self, cik: int) -> Optional[str]:
        """The newest annual-report form on record, or None when unknown.

        Unlike `_detect_filing_type`, which defaults to 10-K for its source
        tags, this says "unknown" — the listing check (A6) must not read a
        missing submissions file as proof of a domestic filer.
        """
        data = self._get_json(_SUBMISSIONS_URL.format(cik=cik), f"submissions_{cik}")
        if data is None:
            return None
        for form in data.get("filings", {}).get("recent", {}).get("form", []) or []:
            base = str(form).split("/")[0].strip().upper()
            if base in ANNUAL_FORMS:
                return base
        return None

    def use_exchange_file(self, data: dict) -> int:
        """Use a saved company_tickers_exchange.json instead of downloading it
        (resolve_tickers.py --sec-file). Returns the number of rows loaded."""
        rows = parse_exchange_file(data)
        by_ticker: dict[str, TickerRow] = {}
        for row in rows:
            by_ticker.setdefault(row.ticker, row)
        self._rows_by_ticker = by_ticker
        self._name_index = None
        return len(rows)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - elapsed)
        self._last_request_ts = time.monotonic()
        self._request_count += 1

    def _get_json(self, url: str, cache_key: str,
                  max_age_s: Optional[float] = None) -> Optional[dict]:
        cache_path = self._cache / f"{cache_key}.json"
        stale: Optional[dict] = None
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            age = time.time() - cache_path.stat().st_mtime
            if max_age_s is None or age <= max_age_s:
                return data
            stale = data
        if self._offline:
            return stale
        if self._request_count >= _RUNAWAY_REQUEST_GUARD:
            if not self._guard_warned:
                log.warning("EDGAR runaway guard reached (%d requests this run) — "
                            "further requests skipped", _RUNAWAY_REQUEST_GUARD)
                self._guard_warned = True
            return stale

        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            self._throttle()
            try:
                resp = self._session.get(url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    cache_path.write_text(json.dumps(data))
                    return data
                if resp.status_code == 429:
                    log.warning("EDGAR 429 on attempt %d for %s", attempt + 1, url)
                    continue
                if resp.status_code == 404:
                    return stale
                log.warning("EDGAR HTTP %d for %s", resp.status_code, url)
                break
            except Exception as e:
                log.warning("EDGAR request error attempt %d: %s", attempt + 1, e)
        if stale is not None:
            log.warning("EDGAR refresh failed for %s — using the stale cache", cache_key)
        return stale

    def _load_ticker_map(self):
        if self._rows_by_ticker is not None:
            return
        data = self._get_json(_TICKER_MAP_URL, _TICKER_MAP_CACHE_KEY,
                              max_age_s=_TICKER_MAP_TTL_S)
        rows = parse_exchange_file(data)
        if not rows:
            # Without the map every ticker would silently fall back to yfinance
            # (F14) — say so loudly instead.
            log.warning("SEC ticker map unavailable (%s) — EDGAR cannot resolve "
                        "any ticker this run", _TICKER_MAP_URL)
        by_ticker: dict[str, TickerRow] = {}
        for row in rows:
            by_ticker.setdefault(row.ticker, row)
        self._rows_by_ticker = by_ticker

    def _resolve_cik(self, ticker: str) -> Optional[int]:
        row = self.lookup_ticker(ticker)
        return row.cik if row else None

    def _detect_filing_type(self, cik: int) -> str:
        """The issuer's annual-report form: "10-K", "20-F" or "40-F".

        `recent.form` on the submissions endpoint lists filings newest first,
        so the first annual form found is the current one — an issuer that
        moved from 20-F to 10-K reads as domestic. The `files` sibling array
        holds references to other JSON files, not forms, and is not read. With
        no annual form on record we conservatively default to 10-K.
        """
        if cik in self._filing_types:
            return self._filing_types[cik]
        data = self._get_json(_SUBMISSIONS_URL.format(cik=cik), f"submissions_{cik}")
        form_type = "10-K"
        if data is not None:
            recent_forms = data.get("filings", {}).get("recent", {}).get("form", []) or []
            for form in recent_forms:
                base = str(form).split("/")[0].strip().upper()
                if base in ANNUAL_FORMS:
                    form_type = base
                    break
        self._filing_types[cik] = form_type
        return form_type

    def _get_company_facts(self, cik: int) -> Optional[dict]:
        return self._get_json(
            _COMPANY_FACTS_URL.format(cik=cik),
            f"facts_{cik}",
        )

    def _extract_annual_series(
        self,
        facts: dict,
        concept: str,
        n_years: int,
        asof: date,
        taxonomy: str = "us-gaap",
    ) -> list[Optional[float]]:
        """Up to n_years of annual values ending at or before asof, oldest first.

        XBRL exposes a value once per unit, so iterating over every unit would
        pull in foreign-currency duplicates. One unit is used for the whole
        series — USD when present, else the concept's own reporting currency —
        and units never mix.
        """
        by_unit = _series_by_unit(facts, taxonomy, concept, asof, ANNUAL_FORMS, True)
        unit = pick_unit(by_unit)
        values = by_unit.get(unit, {}) if unit else {}
        ends = sorted(values)[-n_years:]
        result: list[Optional[float]] = [values[e] for e in ends]
        return [None] * (n_years - len(result)) + result

    def _first_concept(
        self, facts: dict, taxonomy: str, item: str, asof: date, annual_duration: bool,
        forms: tuple[str, ...] = ANNUAL_FORMS,
    ) -> tuple[Optional[str], dict[str, dict[date, float]]]:
        """The first candidate concept of `item` with current data, and its series.

        Candidates are tried in the spec's order. The first whose latest period
        is current (see `_CURRENT_WITHIN_DAYS`) wins; when none is current, the
        first with any data does.
        """
        found = []
        for concept in CONCEPTS[item].get(taxonomy, ()):
            series = _series_by_unit(facts, taxonomy, concept, asof, forms, annual_duration)
            if series:
                found.append((concept, series))
        return _prefer_current(found, asof)

    def _debt_series(
        self, facts: dict, taxonomy: str, asof: date,
    ) -> dict[str, dict[date, float]]:
        """Long-term debt by unit and balance-sheet date.

        us-gaap: `LongTermDebt`; else `LongTermDebtNoncurrent`, plus
        `LongTermDebtCurrent` on dates where both exist. ifrs-full: the first
        candidate with data. Current data is preferred throughout.
        """
        if taxonomy != "us-gaap":
            return self._first_concept(facts, taxonomy, "debt", asof, False,
                                       _BALANCE_SHEET_FORMS)[1]

        def series(concept: str) -> dict[str, dict[date, float]]:
            return _series_by_unit(facts, taxonomy, concept, asof,
                                   _BALANCE_SHEET_FORMS, False)

        total = series("LongTermDebt")
        noncurrent = series("LongTermDebtNoncurrent")
        current = series("LongTermDebtCurrent")
        combined = UnitSeries(n_facts=noncurrent.n_facts)
        for unit, values in noncurrent.items():
            extra = current.get(unit, {})
            combined[unit] = {end: v + extra.get(end, 0.0) for end, v in values.items()}
        found = [(name, s) for name, s in (("LongTermDebt", total),
                                           ("LongTermDebtNoncurrent", combined)) if s]
        return _prefer_current(found, asof)[1]

    def _build_record(
        self, ticker: str, cik: int, asof: date, facts: dict, filing_type: str
    ) -> Optional[FundamentalsRecord]:
        source_tag = f"edgar:{filing_type}-{asof.year}"
        conf = self.base_confidence
        is_adr = filing_type == "20-F"

        # Taxonomy: us-gaap first, then ifrs-full — but a taxonomy whose data
        # stopped years ago never beats a current one (Toyota and Sony moved
        # from US GAAP to IFRS in 2020-21; their us-gaap facts end there).
        # Net income and equity always come from one taxonomy.
        options = []
        for taxonomy in TAXONOMIES:
            _, ni = self._first_concept(facts, taxonomy, "net_income", asof, True)
            _, eq = self._first_concept(facts, taxonomy, "equity", asof, False)
            if ni or eq:
                options.append((taxonomy, ni, eq))
        horizon = asof - timedelta(days=_CURRENT_WITHIN_DAYS)

        def current(series) -> bool:
            return bool(series) and max(max(v) for v in series.values()) >= horizon

        chosen: Optional[str] = None
        ni_series: dict[str, dict[date, float]] = {}
        eq_series: dict[str, dict[date, float]] = {}
        for test in (lambda ni, eq: ni and eq and current(ni),
                     lambda ni, eq: ni and current(ni),
                     lambda ni, eq: ni and eq,
                     lambda ni, eq: ni,
                     lambda ni, eq: eq):
            match = next((o for o in options if test(o[1], o[2])), None)
            if match:
                chosen, ni_series, eq_series = match
                break

        # ROE per fiscal year, numerator and denominator in one shared unit.
        # Without a shared unit, net income keeps its own unit and ROE stays
        # undefined rather than mixing currencies.
        pair_unit = pick_unit(ni_series, eq_series) if (ni_series and eq_series) else None
        unit = pair_unit or pick_unit(ni_series)
        ni_map = ni_series.get(unit, {}) if unit else {}
        eq_map = eq_series.get(pair_unit, {}) if pair_unit else {}
        ends = sorted(ni_map)[-_N_YEARS:]

        roe_5y: list[Optional[DataPoint]] = []
        undefined_years: list[int] = []
        for end in ends:
            eq = eq_map.get(end)
            if eq is not None and eq <= 0:
                # F10: a loss over negative equity would read as a positive ROE.
                undefined_years.append(end.year)
                eq = None
            if eq is None:
                roe_5y.append(DataPoint(value=None, confidence=0.0, source=source_tag,
                                        asof=asof, period_end=end))
            else:
                roe_5y.append(DataPoint(value=round(ni_map[end] / eq, 4), confidence=conf,
                                        source=source_tag, asof=asof, period_end=end))
        roe_5y = [DataPoint(value=None, confidence=0.0, source=source_tag, asof=asof)
                  ] * (_N_YEARS - len(roe_5y)) + roe_5y

        # Net income 5y (raw, for the persistence check), in the same unit.
        ni_5y: list[Optional[DataPoint]] = [
            DataPoint(value=ni_map[end], confidence=conf, source=source_tag, asof=asof,
                      period_end=end)
            for end in ends
        ]
        ni_5y = [None] * (_N_YEARS - len(ni_5y)) + ni_5y

        # Debt/Equity at the latest balance-sheet date where both exist in one
        # unit — and never when the latest equity is zero or negative, so a
        # negative ratio cannot slip under the screen's ceiling.
        de_dp = None
        if chosen is not None:
            eq_bs = self._first_concept(facts, chosen, "equity", asof, False,
                                        _BALANCE_SHEET_FORMS)[1]
            debt_bs = self._debt_series(facts, chosen, asof)
            de_unit = pick_unit(debt_bs, eq_bs)
            if de_unit:
                equity_by_end = eq_bs[de_unit]
                latest = max(equity_by_end)
                if equity_by_end[latest] > 0:
                    common = [e for e in sorted(set(debt_bs[de_unit]) & set(equity_by_end))
                              if (latest - e).days <= _DE_MAX_GAP_DAYS]
                    if common and equity_by_end[common[-1]] > 0:
                        end = common[-1]
                        de_dp = DataPoint(
                            value=round(debt_bs[de_unit][end] / equity_by_end[end], 4),
                            confidence=conf, source=source_tag, asof=asof,
                        )

        has_roe = any(dp.value is not None for dp in roe_5y)
        has_ni = any(dp is not None for dp in ni_5y)
        if not (has_roe or has_ni or de_dp is not None):
            return None

        # EV/EBITDA — EDGAR doesn't provide this directly; leave None so the
        # registry fills it from yfinance.
        # Industry: SIC lives in the submissions endpoint, not company-facts, so
        # EDGAR provides no industry here; the registry back-fills it.
        return FundamentalsRecord(
            ticker=ticker,
            asof=asof,
            roe_5y=roe_5y,
            ev_ebitda=None,
            debt_equity=de_dp,
            net_income_5y=ni_5y,
            industry=normalize_industry(None),
            is_adr=is_adr,
            # data_asof: the latest fiscal year end of the series actually used
            # — the real "as of" of the data, distinct from the request date
            # (M4 L2). Falls back to a scan of every annual fact.
            data_asof=max(ni_map) if ni_map else self._latest_filing_end_date(facts, asof),
            roe_undefined_years=undefined_years,
            taxonomy=chosen,
            reporting_currency=unit,
        )

    def _latest_filing_end_date(
        self, facts: dict, asof: date,
    ) -> Optional[date]:
        """Latest annual-report period end on or before asof, over both
        taxonomies and every currency unit."""
        latest: Optional[date] = None
        for taxonomy in TAXONOMIES:
            for concept_data in (facts.get("facts") or {}).get(taxonomy, {}).values():
                for unit, unit_vals in (concept_data.get("units") or {}).items():
                    if not _ISO4217_RE.match(unit):
                        continue
                    for item in unit_vals:
                        if item.get("form") not in ANNUAL_FORMS:
                            continue
                        end_raw = item.get("end")
                        if not end_raw:
                            continue
                        try:
                            end = date.fromisoformat(end_raw)
                        except ValueError:
                            continue
                        if end <= asof and (latest is None or end > latest):
                            latest = end
        return latest
