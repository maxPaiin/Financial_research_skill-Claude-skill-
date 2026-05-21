"""
EDGAR provider — true point-in-time US fundamentals via SEC EDGAR.

Contract (canonical per §5.3):
- User-Agent: "FinancialResearchSkill-v0.2 anthropic-claude-skill"
- Throttle: minimum 100 ms between requests (≤ 10 req/s, SEC fair-use)
- Daily budget per session: 600 requests max
- Cache: permanent by (ticker, filing_id) — filings are immutable
- Supports: 10-K (domestic US) and 20-F (ADR / foreign filers)
- Retry on HTTP 429: exponential 1s → 2s → 4s, then fall through to yfinance
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

import requests

from .base import DataPoint, FundamentalsRecord, FundamentalsProvider, DEFAULT_CONFIDENCE
from .industry_map import normalize as normalize_industry

log = logging.getLogger(__name__)

# Canonical constants — do not duplicate elsewhere.
_USER_AGENT = "FinancialResearchSkill-v0.2 anthropic-claude-skill"
_MIN_INTERVAL_S = 0.10          # 100 ms between requests
_DAILY_BUDGET = 600             # max requests per session
_RETRY_DELAYS = [1.0, 2.0, 4.0]
_EDGAR_BASE = "https://data.sec.gov"
_COMPANY_FACTS_URL = _EDGAR_BASE + "/api/xbrl/companyfacts/CIK{cik:010d}.json"
_SUBMISSIONS_URL = _EDGAR_BASE + "/submissions/CIK{cik:010d}.json"
_TICKER_MAP_URL = _EDGAR_BASE + "/files/company_tickers.json"

# Default cache lives at <repo-root>/.cache/edgar so the provider can be
# instantiated outside the Claude skill runtime (the old /home/claude/work/...
# default failed on every other host). Override via the `cache_dir=` kwarg or
# the EDGAR_CACHE_DIR env var when needed.
_DEFAULT_CACHE_DIR = (
    Path(__file__).resolve().parents[2] / ".cache" / "edgar"
)
_CACHE_DIR = Path(os.environ["EDGAR_CACHE_DIR"]) if os.environ.get("EDGAR_CACHE_DIR") else _DEFAULT_CACHE_DIR


class EDGARProvider(FundamentalsProvider):
    """Fetches fundamentals from SEC EDGAR with caching and throttling."""

    def __init__(self, cache_dir: Path = _CACHE_DIR):
        self._cache = cache_dir
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ticker_to_cik: dict[str, int] = {}
        self._last_request_ts: float = 0.0
        self._request_count: int = 0
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

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
            if self._request_count >= _DAILY_BUDGET:
                log.warning("EDGAR daily budget exhausted (%d requests)", _DAILY_BUDGET)
                return None

            filing_type = self._detect_filing_type(cik)
            facts = self._get_company_facts(cik)
            if facts is None:
                return None

            record = self._build_record(ticker, cik, asof, facts, filing_type)
            return record
        except Exception as e:
            log.warning("EDGAR fetch failed for %s: %s", ticker, e)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < _MIN_INTERVAL_S:
            time.sleep(_MIN_INTERVAL_S - elapsed)
        self._last_request_ts = time.monotonic()
        self._request_count += 1

    def _get_json(self, url: str, cache_key: str) -> Optional[dict]:
        cache_path = self._cache / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text())

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
                    return None
                log.warning("EDGAR HTTP %d for %s", resp.status_code, url)
                return None
            except Exception as e:
                log.warning("EDGAR request error attempt %d: %s", attempt + 1, e)
        return None

    def _load_ticker_map(self):
        if self._ticker_to_cik:
            return
        data = self._get_json(_TICKER_MAP_URL, "ticker_map")
        if data:
            for entry in data.values():
                t = entry.get("ticker", "").upper()
                c = entry.get("cik_str")
                if t and c:
                    self._ticker_to_cik[t] = int(c)

    def _resolve_cik(self, ticker: str) -> Optional[int]:
        self._load_ticker_map()
        return self._ticker_to_cik.get(ticker.upper())

    def _detect_filing_type(self, cik: int) -> str:
        """Inspect the recent-filings list to decide between 10-K (domestic)
        and 20-F (foreign filer / ADR). The `files` sibling array on the
        submissions endpoint contains references to *other* JSON files, not
        more filing dicts, so the previous attempt to splat it into this
        loop was a no-op. For active filers, `recent.form` is sufficient;
        for filers with no recent filings we conservatively default to 10-K
        (and the upstream record will be sparse anyway, so quality screen
        will catch it).
        """
        data = self._get_json(
            _SUBMISSIONS_URL.format(cik=cik),
            f"submissions_{cik}",
        )
        if data is None:
            return "10-K"
        recent_forms = data.get("filings", {}).get("recent", {}).get("form", []) or []
        if "20-F" in recent_forms:
            return "20-F"
        return "10-K"

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
        allowed_units: tuple[str, ...] = ("USD",),
    ) -> list[Optional[float]]:
        """Extract up to n_years of annual values ending at or before asof.

        SEC XBRL exposes a value once per unit (USD, EUR, USD/shares, shares,
        etc.). Iterating over every unit pulls in foreign-currency duplicates,
        so we restrict to `allowed_units` (USD for dollar-denominated metrics;
        callers pass `("shares",)` for share counts). SEC requires USD
        reporting for both 10-K and 20-F filers, so USD-only is safe.
        """
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        data = us_gaap.get(concept, {}).get("units", {})
        values = []
        for unit, unit_vals in data.items():
            if unit not in allowed_units:
                continue
            for item in unit_vals:
                if item.get("form") in ("10-K", "20-F") and item.get("end"):
                    try:
                        end = date.fromisoformat(item["end"])
                        if end <= asof:
                            values.append((end, item.get("val")))
                    except ValueError:
                        pass
        values.sort(key=lambda x: x[0], reverse=True)
        seen_years: set[int] = set()
        result = []
        for end, val in values:
            if end.year not in seen_years and len(result) < n_years:
                seen_years.add(end.year)
                result.append(val)
        result.reverse()
        while len(result) < n_years:
            result.insert(0, None)
        return result[-n_years:]

    def _extract_latest(
        self,
        facts: dict,
        concept: str,
        asof: date,
        allowed_units: tuple[str, ...] = ("USD",),
    ) -> Optional[float]:
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        data = us_gaap.get(concept, {}).get("units", {})
        best: Optional[tuple[date, float]] = None
        for unit, unit_vals in data.items():
            if unit not in allowed_units:
                continue
            for item in unit_vals:
                if item.get("form") in ("10-K", "20-F", "10-Q") and item.get("end"):
                    try:
                        end = date.fromisoformat(item["end"])
                        if end <= asof:
                            if best is None or end > best[0]:
                                v = item.get("val")
                                if v is not None:
                                    best = (end, v)
                    except ValueError:
                        pass
        return best[1] if best else None

    def _build_record(
        self, ticker: str, cik: int, asof: date, facts: dict, filing_type: str
    ) -> FundamentalsRecord:
        source_tag = f"edgar:{filing_type}-{asof.year}"
        conf = self.base_confidence
        is_adr = filing_type == "20-F"

        # ROE 5y: NetIncome / StockholdersEquity per year
        net_income_vals = self._extract_annual_series(facts, "NetIncomeLoss", 5, asof)
        equity_vals = self._extract_annual_series(facts, "StockholdersEquity", 5, asof)

        roe_5y: list[Optional[DataPoint]] = []
        for ni, eq in zip(net_income_vals, equity_vals):
            if ni is not None and eq and eq != 0:
                roe_dp = DataPoint(
                    value=round(ni / eq, 4),
                    confidence=conf,
                    source=source_tag,
                    asof=asof,
                )
            else:
                roe_dp = DataPoint(value=None, confidence=0.0, source=source_tag, asof=asof)
            roe_5y.append(roe_dp)

        # Net income 5y (raw, for persistence check)
        ni_5y: list[Optional[DataPoint]] = [
            DataPoint(value=v, confidence=conf, source=source_tag, asof=asof)
            if v is not None else None
            for v in net_income_vals
        ]

        # EV/EBITDA — EDGAR doesn't provide this directly; leave None so resolver uses yfinance
        ev_ebitda = None

        # Debt/Equity
        total_debt = self._extract_latest(facts, "LongTermDebt", asof)
        equity_latest = self._extract_latest(facts, "StockholdersEquity", asof)
        de_dp = None
        if total_debt is not None and equity_latest and equity_latest != 0:
            de_dp = DataPoint(
                value=round(total_debt / equity_latest, 4),
                confidence=conf,
                source=source_tag,
                asof=asof,
            )

        # Industry: SIC lives in the submissions endpoint, not company-facts,
        # so EDGAR provides no industry info at this stage. The registry
        # back-fills it from yfinance when available.
        industry = normalize_industry(None)

        # data_asof: most recent filing period-end across the company's facts.
        # This is the actual "as of" date of the data — distinct from `asof`,
        # which is the request date. M4 Level 2.
        data_asof = self._latest_filing_end_date(facts, asof)

        record = FundamentalsRecord(
            ticker=ticker,
            asof=asof,
            roe_5y=roe_5y,
            ev_ebitda=ev_ebitda,
            debt_equity=de_dp,
            net_income_5y=ni_5y,
            industry=industry,
            is_adr=is_adr,
            data_asof=data_asof,
        )
        return record

    def _latest_filing_end_date(
        self, facts: dict, asof: date,
    ) -> Optional[date]:
        """Scan us-gaap facts for the latest 10-K/20-F period-end on or before asof."""
        us_gaap = facts.get("facts", {}).get("us-gaap", {})
        latest: Optional[date] = None
        for concept_data in us_gaap.values():
            for unit, unit_vals in concept_data.get("units", {}).items():
                if unit != "USD":
                    continue
                for item in unit_vals:
                    if item.get("form") not in ("10-K", "20-F"):
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
