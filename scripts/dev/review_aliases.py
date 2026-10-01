"""
Dev tool (v0.4 C4): review alias proposals before they reach references/.

During a run Claude may propose name -> ticker aliases in the work directory's
new_aliases.json — names it saw printed on a factsheet next to a ticker. The
pipeline never uses that file. The maintainer reviews the proposals with this
script and, only if satisfied, merges them into references/ticker_aliases.json
and commits that change. Never imported by the pipeline.

    python scripts/dev/review_aliases.py fr_work/new_aliases.json [--sec-file F] [--merge]

new_aliases.json:
  {"proposals": [{"name": "台積電", "ticker": "TSM", "seen_in": "F3 p2",
                  "why": "ticker printed next to the name"}]}

For each proposal the script prints the SEC row the ticker maps to (issuer
name, exchange), whether the normalised name is already an alias (and to what),
and whether SEC's own issuer names already resolve it. A proposal is rejected
when its ticker is not in SEC's exchange file, when it would re-point an
existing alias, or when its name normalises to nothing. --merge adds the
accepted ones; without it nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.edgar_provider import EDGARProvider, canonical_ticker  # noqa: E402
from providers.names import normalize_company_name  # noqa: E402
from resolve_tickers import DEFAULT_ALIASES, load_aliases  # noqa: E402


def review(proposals: list[dict], provider: EDGARProvider,
           existing: dict[str, str]) -> list[dict]:
    """One verdict per proposal: accept, reject (with why), or already known."""
    out = []
    names = provider.name_index()
    for p in proposals:
        name, ticker = str(p.get("name") or "").strip(), canonical_ticker(str(p.get("ticker") or ""))
        key = normalize_company_name(name)
        row = provider.lookup_ticker(ticker) if ticker else None
        verdict = {"name": name, "ticker": ticker, "key": key, "seen_in": p.get("seen_in"),
                   "sec": f"{row.name} ({row.exchange or 'no exchange'})" if row else None}
        if not key:
            verdict.update(status="reject", why="the name normalises to nothing")
        elif row is None:
            verdict.update(status="reject", why=f"{ticker} is not in SEC's exchange file")
        elif key in existing and existing[key] != ticker:
            verdict.update(status="reject",
                           why=f"'{key}' is already an alias of {existing[key]}")
        elif key in existing:
            verdict.update(status="known", why="already an alias")
        elif any(t == ticker for _, t, _ in names.get(key, [])):
            verdict.update(status="known", why="SEC's issuer name already resolves it")
        else:
            verdict.update(status="accept", why="new alias")
        out.append(verdict)
    return out


def merge(accepted: list[dict], alias_path: Path) -> int:
    data = json.loads(alias_path.read_text(encoding="utf-8"))
    aliases = data.setdefault("aliases", {})
    added = 0
    for v in accepted:
        if v["name"] not in aliases:
            aliases[v["name"]] = v["ticker"]
            added += 1
    alias_path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description="Review alias proposals (maintainer only)")
    ap.add_argument("proposals", help="new_aliases.json from a run's work directory")
    ap.add_argument("--sec-file", help="Saved company_tickers_exchange.json (else the cache "
                                       "or the network, with EDGAR_CONTACT_EMAIL)")
    ap.add_argument("--aliases", default=str(DEFAULT_ALIASES))
    ap.add_argument("--merge", action="store_true", help="Add the accepted proposals")
    args = ap.parse_args()

    provider = EDGARProvider(offline=bool(args.sec_file) or None)
    if args.sec_file:
        provider.use_exchange_file(json.loads(Path(args.sec_file).read_text(encoding="utf-8")))
    proposals = json.loads(Path(args.proposals).read_text(encoding="utf-8")).get("proposals", [])
    verdicts = review(proposals, provider, load_aliases(Path(args.aliases)))
    for v in verdicts:
        print(f"{v['status']:<7} {v['name']!r} -> {v['ticker'] or '?'}  [{v['sec'] or 'not in SEC file'}]"
              f"  {v['why']}" + (f"  (seen in {v['seen_in']})" if v.get("seen_in") else ""))
    accepted = [v for v in verdicts if v["status"] == "accept"]
    if args.merge and accepted:
        n = merge(accepted, Path(args.aliases))
        print(f"Merged {n} alias(es) into {args.aliases} — review the diff, then commit it.")
    elif accepted:
        print(f"{len(accepted)} acceptable; rerun with --merge to add them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
