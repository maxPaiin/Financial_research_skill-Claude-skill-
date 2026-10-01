"""
Stage 1b-resolve (v0.4 A6): is each holding a US exchange-listed security?

Before v0.4, "US-listed" was decided by the *format* of the ticker string
written at Stage 1a (F11): the same company was in or out depending on which
ticker was written, and 5-letter OTC tickers and `.PK` lines passed as US.
Here the authority is SEC's company_tickers_exchange.json: a security is kept
only when SEC lists its ticker on Nasdaq, NYSE or CBOE (I5) — including ADRs of
SEC-registered issuers and US-listed shares of companies domiciled abroad.

Each equity row is resolved by the first rule that applies. The ticker is
checked before the ISIN, because a non-US ISIN alone does not mean a non-US
listing: Accenture, Medtronic and Chubb are NYSE-listed with IE/CH ISINs.

1. Ticker present (US suffixes such as " US", ".O", ".N" are stripped):
     SEC lists it on Nasdaq / NYSE / CBOE  -> kept
     SEC lists it on OTC (or an OTC marker such as .PK)  -> otc_only
     SEC row with no exchange               -> no_exchange
     not in the file, non-US form (2330.TW, 0700 HK, 7203)  -> non_us_listing
     not in the file otherwise              -> unresolved_ticker
2. No ticker: the name, normalised (providers/names.py), is matched against
   references/ticker_aliases.json first, then SEC's issuer names.
     several tickers match                  -> ambiguous_name
     nothing matches                        -> unresolved_name
     one match not listed on an exchange    -> otc_only / no_exchange
     one match, issuer files 10-K           -> kept, whatever the ISIN
     one match, foreign private issuer (20-F / 40-F) — or filer type unknown,
     which is treated the same way:
       ADR marker in the name, or a US ISIN -> kept (the fund holds the ADR)
       non-US ISIN                          -> non_us_listing (home-market line)
       neither                              -> ambiguous_listing

Every equity row gets `ticker_resolved`, `listing_exchange` and
`resolution: {method, status, detail}`; extract_holdings.py keeps a row if and
only if its status is `kept`. Rows that need a human look (unresolved and
ambiguous) are printed compactly with their fund, row index and page: Claude
may supply a ticker or ISIN only if it is printed on that factsheet page
(checked with render_page.py), via apply_review.py. Aliases Claude proposes go
to the work directory's new_aliases.json and are NOT used in the run — the
maintainer reviews and commits them.

Usage:
  resolve_tickers.py --holdings holdings.json [--email you@example.com]
                     [--sec-file company_tickers_exchange.json] [--offline]
                     [--aliases references/ticker_aliases.json] [--out PATH]

Network: www.sec.gov (exchange file) unless --sec-file is given, and
data.sec.gov (submissions, for the filer type of name-only rows) unless
cached. --offline uses the cache only; an unknown filer type is treated
conservatively, never as domestic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_holdings import is_non_equity  # noqa: E402
from providers.edgar_provider import (  # noqa: E402
    EDGARProvider, FOREIGN_PRIVATE_ISSUER_FORMS, TickerRow, canonical_ticker,
)
from providers.names import normalize_company_name  # noqa: E402
from validate_uploads import EMAIL_GATE_MESSAGE, valid_email  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALIASES = _REPO_ROOT / "references" / "ticker_aliases.json"

LISTED_EXCHANGES = {"NASDAQ", "NYSE", "CBOE"}
KEPT = "kept"
NEEDS_REVIEW = ("unresolved_ticker", "unresolved_name", "ambiguous_name", "ambiguous_listing")

# Bloomberg-style "<ticker> <code>": US composite / exchange codes.
_US_BBG_CODES = {"US", "UW", "UN", "UQ", "UR", "UA", "UP", "UF", "UV", "UD"}
# Reuters/other US exchange suffixes, stripped before the lookup.
_US_DOT_SUFFIXES = (".O", ".N", ".OQ", ".K", ".A.N")
# OTC markers: the line is over-the-counter whatever else is known.
_OTC_SUFFIXES = (".PK", ".OB", ".PINK", ".OTC")
# Non-US exchange suffixes (Yahoo / Reuters forms).
_NON_US_SUFFIXES = {
    "T", "HK", "TW", "TWO", "L", "SS", "SZ", "SH", "PA", "DE", "AS", "MI", "MC",
    "TO", "AX", "KS", "KQ", "SI", "BK", "SW", "S", "CO", "ST", "HE", "OL", "BR",
    "LS", "VI", "IR", "NZ", "SA", "MX", "JK", "NS", "BO", "KL", "V", "NE", "F",
    "XETRA", "TYO", "LN",
}
_ADR_MARKER_RE = re.compile(r"\b(?:ADRs?|ADSs?|American\s+Depositary)\b", re.IGNORECASE)
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def load_aliases(path: Path = DEFAULT_ALIASES) -> dict[str, str]:
    """normalised name -> canonical ticker."""
    if not path or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, ticker in (data.get("aliases") or {}).items():
        key = normalize_company_name(name)
        if key and ticker:
            out[key] = canonical_ticker(str(ticker))
    return out


def parse_ticker(raw: Optional[str]) -> tuple[Optional[str], str]:
    """(lookup form, hint) for a ticker as written on the factsheet.

    hint: "us" (a US suffix was stripped), "otc" (an OTC marker), "non_us_code"
    (a Bloomberg non-US exchange code — decisive: "VOD LN" is the London line
    even though SEC lists Vodafone's ADR as VOD), "non_us_suffix" (a dotted
    non-US suffix — looked up first, since "MKC.V" is a real NYSE class), or ""
    (no marker).
    """
    t = (raw or "").strip().upper()
    if not t:
        return None, ""
    t = re.sub(r"\s+EQUITY$", "", t).strip()
    m = re.match(r"^([A-Z0-9./-]+)\s+([A-Z]{2})$", t)            # Bloomberg form
    if m:
        base, code = m.groups()
        return base.replace("/", "."), ("us" if code in _US_BBG_CODES else "non_us_code")
    for suffix in _OTC_SUFFIXES:
        if t.endswith(suffix):
            return t[: -len(suffix)], "otc"
    for suffix in _US_DOT_SUFFIXES:
        if t.endswith(suffix) and len(t) > len(suffix):
            return t[: -len(suffix)], "us"
    if "." in t and t.rpartition(".")[2] in _NON_US_SUFFIXES:
        return t, "non_us_suffix"
    return t, ""


def _status_for_exchange(exchange: Optional[str]) -> str:
    if exchange and exchange.upper() in LISTED_EXCHANGES:
        return KEPT
    if exchange and exchange.upper() == "OTC":
        return "otc_only"
    return "no_exchange"


class ListingResolver:
    """Resolves holdings rows against SEC's exchange file (see module doc)."""

    def __init__(
        self,
        lookup: Callable[[str], Optional[TickerRow]],
        name_index: Callable[[], dict[str, list[tuple[int, str, Optional[str]]]]],
        annual_form: Callable[[int], Optional[str]],
        aliases: Optional[dict[str, str]] = None,
    ):
        self._lookup = lookup
        self._name_index = name_index
        self._annual_form = annual_form
        self._aliases = aliases or {}

    @classmethod
    def from_provider(cls, provider: EDGARProvider,
                      aliases: Optional[dict[str, str]] = None) -> "ListingResolver":
        return cls(provider.lookup_ticker, provider.name_index, provider.annual_form, aliases)

    # --- one row ----------------------------------------------------------

    def resolve_row(self, row: dict) -> dict:
        """{ticker_resolved, listing_exchange, resolution} for one holdings row."""
        raw = row.get("ticker_raw") or row.get("ticker")
        if raw and str(raw).strip():
            return self._by_ticker(str(raw))
        return self._by_name(row)

    def _out(self, ticker, exchange, method, status, detail) -> dict:
        return {"ticker_resolved": ticker, "listing_exchange": exchange,
                "resolution": {"method": method, "status": status, "detail": detail}}

    def _by_ticker(self, raw: str) -> dict:
        form, hint = parse_ticker(raw)
        if form is None:
            return self._out(None, None, "ticker", "unresolved_ticker", "empty ticker")
        if hint == "non_us_code":
            return self._out(None, None, "ticker", "non_us_listing",
                             f"{raw} carries a non-US exchange code")
        sec = self._lookup(form)
        if sec is not None:
            status = _status_for_exchange(sec.exchange)
            if status == KEPT and hint == "otc":
                status = "otc_only"      # the row names an OTC line explicitly
            where = sec.exchange or "no exchange"
            return self._out(sec.ticker, sec.exchange, "ticker", status,
                             f"SEC lists {sec.ticker} on {where}")
        if hint == "otc":
            return self._out(canonical_ticker(form), None, "ticker", "otc_only",
                             f"{raw} is an over-the-counter line")
        if hint == "non_us_suffix" or form.split(".")[0].isdigit():
            return self._out(None, None, "ticker", "non_us_listing",
                             f"{raw} is a non-US exchange line")
        return self._out(None, None, "ticker", "unresolved_ticker",
                         f"{canonical_ticker(form)} is not in SEC's exchange file")

    def _by_name(self, row: dict) -> dict:
        name = row.get("name") or ""
        key = normalize_company_name(name)
        if not key:
            return self._out(None, None, "name", "unresolved_name", "no name to match")

        if key in self._aliases:
            method, alias_ticker = "alias", self._aliases[key]
            sec = self._lookup(alias_ticker)
            if sec is None:
                return self._out(None, None, method, "unresolved_name",
                                 f"alias {alias_ticker} is not in SEC's exchange file")
            matches = [(sec.cik, sec.ticker, sec.exchange)]
        else:
            method = "name"
            matches = self._name_index().get(key, [])

        tickers = sorted({t for _, t, _ in matches})
        if not tickers:
            return self._out(None, None, method, "unresolved_name",
                             f"no SEC issuer named '{key}'")
        if len(tickers) > 1:
            return self._out(None, None, method, "ambiguous_name",
                             f"'{key}' matches {', '.join(tickers)}")

        cik, ticker, exchange = matches[0]
        listed = _status_for_exchange(exchange)
        if listed != KEPT:
            return self._out(ticker, exchange, method, listed,
                             f"{ticker} is not exchange-listed ({exchange or 'no exchange'})")

        form = self._annual_form(cik)
        if form == "10-K":
            return self._out(ticker, exchange, method, KEPT,
                             f"domestic filer; SEC lists {ticker} on {exchange}")

        filer = form if form in FOREIGN_PRIVATE_ISSUER_FORMS else "unknown filer type"
        isin = (row.get("isin") or "").strip().upper()
        if _ADR_MARKER_RE.search(name) or (isin and isin.startswith("US")):
            evidence = "ADR marker" if _ADR_MARKER_RE.search(name) else "US ISIN"
            return self._out(ticker, exchange, method, KEPT,
                             f"{filer}; {evidence} -> the fund holds {ticker}")
        if isin and _ISIN_RE.match(isin):
            return self._out(ticker, exchange, method, "non_us_listing",
                             f"{filer}; {isin[:2]} ISIN -> the fund holds the home-market share")
        return self._out(ticker, exchange, method, "ambiguous_listing",
                         f"{filer}; no ISIN or ADR marker -> cannot tell whether the "
                         f"fund holds {ticker} or the home-market share")

    # --- a whole holdings.json ---------------------------------------------

    def resolve_holdings(self, data: dict) -> dict:
        """Resolve every equity row of every fund, in place. Returns `data`."""
        for fund in data.get("funds", []):
            for row in fund.get("holdings", []):
                if is_non_equity(row):
                    continue          # extract_holdings drops these as non-equity
                row.update(self.resolve_row(row))
        return data


def summarize(data: dict) -> tuple[list[str], list[str]]:
    """(per-fund count lines, rows needing review) for the console."""
    counts_lines: list[str] = []
    review: list[str] = []
    for fund in data.get("funds", []):
        counts: dict[str, int] = {}
        for i, row in enumerate(fund.get("holdings", [])):
            res = row.get("resolution")
            if not res:
                continue
            counts[res["status"]] = counts.get(res["status"], 0) + 1
            if res["status"] in NEEDS_REVIEW:
                page = f" p{row['page']}" if row.get("page") else ""
                label = row.get("ticker_raw") or row.get("name") or "?"
                review.append(f"{fund.get('fund_id')}.holdings[{i}]{page} "
                              f"\"{label}\" — {res['status']}: {res['detail']}")
        counts_lines.append(
            f"{fund.get('fund_id')}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return counts_lines, review


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 1b-resolve: SEC listing check (v0.4 A6)")
    ap.add_argument("--holdings", required=True, help="holdings.json from Stage 1a")
    ap.add_argument("--sec-file", help="Saved company_tickers_exchange.json (replay; "
                                       "skips the download).")
    ap.add_argument("--email", default=os.environ.get("EDGAR_CONTACT_EMAIL"),
                    help="SEC contact email (User-Agent only). Falls back to "
                         "EDGAR_CONTACT_EMAIL.")
    ap.add_argument("--offline", action="store_true",
                    help="Use the EDGAR cache only; never the network.")
    ap.add_argument("--aliases", default=str(DEFAULT_ALIASES),
                    help="Curated alias file (default: references/ticker_aliases.json).")
    ap.add_argument("--out", help="Output path (defaults to overwrite --holdings).")
    args = ap.parse_args()

    if not args.offline and not valid_email(args.email):
        print(EMAIL_GATE_MESSAGE, file=sys.stderr)
        return 2

    provider = EDGARProvider(contact_email=args.email, offline=args.offline or None)
    if args.sec_file:
        n = provider.use_exchange_file(json.loads(Path(args.sec_file).read_text(encoding="utf-8")))
        if not n:
            print(f"ERROR: {args.sec_file} has no usable rows", file=sys.stderr)
            return 1
    elif provider.lookup_ticker("AAPL") is None:
        print("ERROR: SEC's exchange file could not be loaded — the listing check cannot "
              "run. Retry, or pass --sec-file.", file=sys.stderr)
        return 1

    path = Path(args.holdings)
    data = json.loads(path.read_text(encoding="utf-8"))
    resolver = ListingResolver.from_provider(provider, load_aliases(Path(args.aliases)))
    resolver.resolve_holdings(data)

    out = Path(args.out) if args.out else path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    counts_lines, review = summarize(data)
    print(f"Listing check (SEC exchange file) -> {out}")
    for line in counts_lines:
        print("  " + line)
    if review:
        print(f"Rows needing review ({len(review)}): supply a ticker or ISIN only if it is "
              "printed on that page (render_page.py), via apply_review.py")
        for line in review[:40]:
            print("  " + line)
        if len(review) > 40:
            print(f"  ... {len(review) - 40} more in {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
