"""
Dev tool (v0.4 A2): record trimmed SEC fixtures for the offline test suite.

    python scripts/dev/record_fixtures.py --email you@example.com

Needs network access to www.sec.gov and data.sec.gov. Never imported by the
pipeline. Writes to tests/fixtures/edgar/ (or --out):

  company_tickers_exchange_sample.json   trimmed SEC exchange file (A6 tests)
  facts_<CIK>.json, submissions_<CIK>.json for
    - a 10-K USD filer (Apple),
    - TSMC (CIK 1046179; IFRS, TWD),
    - the first of MCD / AZO / SBUX whose equity was <= 0 in at least one of
      its last five fiscal years (checked here, not assumed),
  manifest.json                          what was recorded, when, and what each
                                         fixture yields through the provider

companyfacts are trimmed to the concepts the provider reads (last eight years
of each); submissions to the form list. The contact email goes into the SEC
User-Agent header and nowhere else: every written file is checked for it.

It also prints a concept census over a wider set of real filers, so the
candidate lists in providers/edgar_provider.CONCEPTS can be checked against
real filings (A2.3), plus what the provider extracts for each filer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.edgar_provider import (  # noqa: E402
    ANNUAL_FORMS, CONCEPTS, TAXONOMIES, EDGARProvider, _TICKER_MAP_CACHE_KEY,
    _TICKER_MAP_URL, _series_by_unit,
)
from validate_uploads import valid_email  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = _REPO_ROOT / "tests" / "fixtures" / "edgar"
_ALIASES = _REPO_ROOT / "references" / "ticker_aliases.json"

USD_10K = "AAPL"
IFRS_TWD = "TSM"                 # Taiwan Semiconductor Manufacturing, CIK 1046179
NEGATIVE_EQUITY_CANDIDATES = ("MCD", "AZO", "SBUX")

# Rows kept in the exchange-file sample: what the A6 listing tests and the
# alias seed need, plus a spread of large US and foreign-domiciled listings.
SAMPLE_TICKERS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO",
    "TSM", "ASML", "ACN", "MDT", "CB", "TCEHY", "BRK-A", "BRK-B", "BF-B",
    "MCD", "AZO", "SBUX", "ORCL", "CRM", "AMD", "ADBE", "NFLX", "INTC",
    "QCOM", "TXN", "CSCO", "IBM", "NOW", "INTU", "AMAT", "LRCX", "KLAC",
    "MU", "ARM", "SHOP", "UBER", "PLTR", "BABA", "PDD", "JD", "NVO", "SAP",
    "SONY", "TM", "JPM", "V", "MA", "LLY", "UNH", "COST", "WMT", "NU",
)
# Filers whose companyfacts are downloaded only for the census (not saved).
CENSUS_TICKERS = (
    "AAPL", "MSFT", "JPM", "BRK-B", "ACN", "TSM", "ASML", "NVO", "SAP", "TM",
    "SONY", "SHEL", "UL", "BHP", "CNQ", "ENB", "MCD", "AZO", "SBUX",
)
_KEEP_YEARS = 8
_FORMS_KEPT = 60


def _alias_tickers() -> set[str]:
    if not _ALIASES.exists():
        return set()
    data = json.loads(_ALIASES.read_text(encoding="utf-8"))
    return {str(t).upper() for t in (data.get("aliases") or {}).values()}


def trim_facts(facts: dict) -> dict:
    """Keep only the provider's candidate concepts, last `_KEEP_YEARS` years."""
    concepts = {tax: set() for tax in TAXONOMIES}
    for item in CONCEPTS.values():
        for tax, names in item.items():
            concepts[tax].update(names)
    out = {"cik": facts.get("cik"), "entityName": facts.get("entityName"), "facts": {}}
    for tax in TAXONOMIES:
        node = (facts.get("facts") or {}).get(tax) or {}
        kept_tax = {}
        for concept in sorted(concepts[tax]):
            if concept not in node:
                continue
            units = node[concept].get("units") or {}
            ends = [it.get("end", "") for vals in units.values() for it in vals]
            latest = max((e for e in ends if e), default="")
            if not latest:
                continue
            floor = f"{int(latest[:4]) - _KEEP_YEARS:04d}"
            kept_units = {}
            for unit, vals in units.items():
                vals = [it for it in vals if (it.get("end") or "") >= floor]
                if vals:
                    kept_units[unit] = vals
            if kept_units:
                kept_tax[concept] = {"label": node[concept].get("label"),
                                     "units": kept_units}
        if kept_tax:
            out["facts"][tax] = kept_tax
    return out


def trim_submissions(sub: dict) -> dict:
    """Keep the newest forms — always through the first annual report, since
    a frequent 6-K filer can push its 20-F past any fixed cut-off."""
    recent = (sub.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    first_annual = next((i for i, f in enumerate(forms)
                         if str(f).split("/")[0] in ANNUAL_FORMS), 0)
    keep = max(_FORMS_KEPT, first_annual + 1)
    return {
        "cik": sub.get("cik"),
        "name": sub.get("name"),
        "tickers": sub.get("tickers"),
        "exchanges": sub.get("exchanges"),
        "filings": {"recent": {
            "form": forms[:keep],
            "filingDate": (recent.get("filingDate") or [])[:keep],
        }},
    }


def census_row(facts: dict, asof: date) -> dict[str, list[str]]:
    """concept -> currency units with annual data in the last five years."""
    horizon = asof - timedelta(days=5 * 366)
    found: dict[str, list[str]] = {}
    for item, by_tax in CONCEPTS.items():
        for tax, names in by_tax.items():
            for concept in names:
                annual = item == "net_income"
                forms = ANNUAL_FORMS if annual else ANNUAL_FORMS + ("10-Q",)
                series = _series_by_unit(facts, tax, concept, asof, forms, annual)
                units = sorted(u for u, vals in series.items()
                               if any(end >= horizon for end in vals))
                if units:
                    found[f"{tax}:{concept}"] = units
    return found


def extraction_summary(provider: EDGARProvider, ticker: str, asof: date) -> dict:
    rec = provider.fetch(ticker, asof)
    if rec is None:
        return {"record": None}
    roe = [dp.value for dp in rec.roe_5y if dp is not None and dp.value is not None]
    return {
        "taxonomy": rec.taxonomy,
        "reporting_currency": rec.reporting_currency,
        "roe_defined_years": len(roe),
        "roe_undefined_years": rec.roe_undefined_years,
        "debt_equity": rec.debt_equity.value if rec.debt_equity else None,
        "data_asof": rec.data_asof.isoformat() if rec.data_asof else None,
    }


def _write(path: Path, payload: dict, email: str) -> None:
    text = json.dumps(payload, indent=1, ensure_ascii=False, sort_keys=False)
    if email.lower() in text.lower():
        raise SystemExit(f"refusing to write {path.name}: it would contain the contact email")
    path.write_text(text + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Record trimmed SEC fixtures (dev only).")
    ap.add_argument("--email", default=os.environ.get("EDGAR_CONTACT_EMAIL"),
                    help="SEC contact email, used in the User-Agent header only.")
    ap.add_argument("--out", default=str(_DEFAULT_OUT), help="Fixture directory.")
    args = ap.parse_args()

    email = (args.email or "").strip()
    if not valid_email(email):
        print("A valid --email (or EDGAR_CONTACT_EMAIL) is required.", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    asof = date.today()

    with tempfile.TemporaryDirectory() as tmp:
        provider = EDGARProvider(cache_dir=Path(tmp), contact_email=email)
        raw_map = provider._get_json(_TICKER_MAP_URL, _TICKER_MAP_CACHE_KEY)
        if not raw_map:
            print("could not download the SEC exchange file", file=sys.stderr)
            return 1

        # 1. Exchange-file sample.
        fields = [str(f).lower() for f in raw_map.get("fields", [])]
        i_tkr, i_exch = fields.index("ticker"), fields.index("exchange")
        wanted = {t.upper() for t in SAMPLE_TICKERS + CENSUS_TICKERS} | _alias_tickers()
        rows = [r for r in raw_map["data"] if str(r[i_tkr]).upper() in wanted]
        # Real examples of each non-listed status: TCEHY, the spec's OTC
        # example, is not an SEC registrant and so is absent from this file.
        null_rows = [r for r in raw_map["data"] if r[i_exch] in (None, "")][:2]
        cboe_rows = [r for r in raw_map["data"] if str(r[i_exch]).upper() == "CBOE"][:2]
        otc_rows = [r for r in raw_map["data"] if str(r[i_exch]).upper() == "OTC"][:3]
        sample = {"fields": raw_map["fields"],
                  "data": rows + null_rows + cboe_rows + otc_rows}
        _write(out / "company_tickers_exchange_sample.json", sample, email)
        missing = sorted(wanted - {str(r[i_tkr]).upper() for r in rows})

        # 2. Negative-equity filer: verified, not assumed.
        negative = None
        for tkr in NEGATIVE_EQUITY_CANDIDATES:
            summary = extraction_summary(provider, tkr, asof)
            if summary.get("roe_undefined_years"):
                negative = tkr
                break

        # 3. Saved fixtures.
        manifest = {
            "recorded_on": asof.isoformat(),
            "recorded_by": "scripts/dev/record_fixtures.py",
            "source": {"ticker_map": _TICKER_MAP_URL,
                       "companyfacts": "https://data.sec.gov/api/xbrl/companyfacts/",
                       "submissions": "https://data.sec.gov/submissions/"},
            "trim": f"provider concepts only, last {_KEEP_YEARS} years; "
                    f"first {_FORMS_KEPT} recent forms",
            "exchange_sample_missing_tickers": missing,
            "fixtures": {},
        }
        roles = {"usd_10k": USD_10K, "ifrs_twd": IFRS_TWD}
        if negative:
            roles["negative_equity"] = negative
        for role, tkr in roles.items():
            row = provider.lookup_ticker(tkr)
            if row is None:
                print(f"{tkr}: not in the SEC exchange file", file=sys.stderr)
                return 1
            facts = provider._get_company_facts(row.cik)
            sub = provider._get_json(
                f"https://data.sec.gov/submissions/CIK{row.cik:010d}.json",
                f"submissions_{row.cik}")
            _write(out / f"facts_{row.cik}.json", trim_facts(facts or {}), email)
            _write(out / f"submissions_{row.cik}.json", trim_submissions(sub or {}), email)
            manifest["fixtures"][role] = {
                "ticker": tkr, "cik": row.cik, "exchange": row.exchange,
                "files": [f"facts_{row.cik}.json", f"submissions_{row.cik}.json"],
                "yields_at_recording": extraction_summary(provider, tkr, asof),
            }
        _write(out / "manifest.json", manifest, email)

        # 4. Census over a wider set of real filers (printed, not saved).
        census: dict[str, dict[str, list[str]]] = {}
        extracted: dict[str, dict] = {}
        for tkr in CENSUS_TICKERS:
            row = provider.lookup_ticker(tkr)
            if row is None:
                continue
            facts = provider._get_company_facts(row.cik)
            if facts:
                census[tkr] = census_row(facts, asof)
                extracted[tkr] = extraction_summary(provider, tkr, asof)
                extracted[tkr]["form"] = provider._detect_filing_type(row.cik)

    print(f"Fixtures written to {out} (recorded {asof.isoformat()}):")
    for role, info in manifest["fixtures"].items():
        print(f"  {role:<16} {info['ticker']:<5} CIK {info['cik']:<8} {info['yields_at_recording']}")
    if not negative:
        print("  negative_equity  NONE of MCD/AZO/SBUX had equity <= 0 in the last five "
              "fiscal years — choose another candidate", file=sys.stderr)
    if missing:
        print(f"  exchange sample: not in the SEC file: {', '.join(missing)}")

    print(f"\nConcept census — filers with annual data in the last 5 years "
          f"(of {len(census)}):")
    for item, by_tax in CONCEPTS.items():
        for tax, names in by_tax.items():
            for concept in names:
                key = f"{tax}:{concept}"
                hits = [t for t, found in census.items() if key in found]
                units = sorted({u for t in hits for u in census[t][key]})
                print(f"  {item:<10} {key:<86} {len(hits):>2}  {','.join(units)}")
    print("\nProvider extraction per census filer:")
    for tkr, summ in extracted.items():
        print(f"  {tkr:<6} {summ}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
