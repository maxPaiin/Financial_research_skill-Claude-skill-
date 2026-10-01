"""
Apply Stage 1a review corrections to holdings.json (v0.4 C3), so nobody
retypes JSON by hand.

    apply_review.py --set F3.currency=USD --set F3.holdings[4].weight=0.031
    apply_review.py --set "F2.benchmark=MSCI ACWI Index" --set F2.holdings[10].name=Visa
    apply_review.py --delete F5.holdings[7]

Paths: <fund_id>.<field> or <fund_id>.holdings[<i>].<field>, with i counted
from 0 as in candidates_summary.md. Setting a field on index == len(holdings)
appends a new row. --delete removes a row; deletions apply after every --set,
from the highest index down, so earlier indices stay valid.

Values: `null` clears a field; a weight may be a fraction (0.031) or a
percentage with its sign (3.1%), and must lie in (0, 1]; total_aum and
nav_per_share are numbers; everything else is text as given. Never set a field
to something the factsheet does not print — `currency` and `benchmark` above
all: if it is not printed, it is null.

Every change is recorded in the fund's `review_log`, and the matching entries
in `review_flags` are cleared.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import work_dir  # noqa: E402

_PATH_RE = re.compile(r"^(?P<fund>[A-Za-z0-9_-]+)\.(?:holdings\[(?P<idx>\d+)\]\.)?(?P<field>[a-z_]+)$")
_ROW_RE = re.compile(r"^(?P<fund>[A-Za-z0-9_-]+)\.holdings\[(?P<idx>\d+)\]$")
_FUND_FIELDS = {"fund_name", "issuer", "asof", "currency", "total_aum", "benchmark", "fund_isin",
                "nav_per_share", "style"}
_ROW_FIELDS = {"name", "ticker_raw", "isin", "weight", "page"}
_NUMERIC = {"total_aum", "nav_per_share"}


class ReviewError(ValueError):
    pass


def parse_value(field: str, raw: str):
    text = raw.strip()
    if text.lower() in ("null", "none", ""):
        return None
    if field == "weight":
        pct = text.endswith("%")
        try:
            value = float(text.rstrip("%").strip())
        except ValueError:
            raise ReviewError(f"weight '{raw}' is not a number")
        value = value / 100.0 if pct else value
        if not 0 < value <= 1:
            raise ReviewError(f"weight '{raw}' must be a fraction in (0, 1] or a percentage "
                              "with %, e.g. 0.031 or 3.1%")
        return round(value, 6)
    if field in _NUMERIC:
        try:
            return float(text.replace(",", ""))
        except ValueError:
            raise ReviewError(f"{field} '{raw}' is not a number")
    if field == "page":
        return int(text)
    return text


def _fund(data: dict, fund_id: str) -> dict:
    for f in data.get("funds", []):
        if f.get("fund_id") == fund_id:
            return f
    raise ReviewError(f"no fund {fund_id} in holdings.json")


def apply(data: dict, sets: list[str], deletes: list[str]) -> list[str]:
    """Apply the corrections in place; return the log lines."""
    log: list[str] = []
    for item in sets:
        path, sep, raw = item.partition("=")
        m = _PATH_RE.match(path.strip())
        if not sep or not m:
            raise ReviewError(f"cannot read '{item}' — expected PATH=VALUE, e.g. "
                              "F3.currency=USD or F3.holdings[4].weight=0.031")
        fund = _fund(data, m.group("fund"))
        field = m.group("field")
        if m.group("idx") is None:
            if field not in _FUND_FIELDS:
                raise ReviewError(f"'{field}' is not a fund field ({', '.join(sorted(_FUND_FIELDS))})")
            fund[field] = parse_value(field, raw)
        else:
            if field not in _ROW_FIELDS:
                raise ReviewError(f"'{field}' is not a holdings field ({', '.join(sorted(_ROW_FIELDS))})")
            rows = fund.setdefault("holdings", [])
            idx = int(m.group("idx"))
            if idx == len(rows):
                rows.append({"name": None, "ticker_raw": None, "isin": None, "weight": None})
            elif idx > len(rows):
                raise ReviewError(f"{fund['fund_id']} has {len(rows)} rows; index {idx} would "
                                  "leave a gap (append at index == len)")
            rows[idx][field] = parse_value(field, raw)
            rows[idx].pop("resolution", None)      # a changed row must be resolved again
            rows[idx].pop("ticker_resolved", None)
            rows[idx].pop("listing_exchange", None)
        _clear_flag(fund, path.strip())
        fund.setdefault("review_log", []).append(f"set {path.strip()}={raw.strip()}")
        log.append(f"set {path.strip()} = {raw.strip()}")

    targets = []
    for item in deletes:
        m = _ROW_RE.match(item.strip())
        if not m:
            raise ReviewError(f"cannot read --delete '{item}' — expected F3.holdings[7]")
        targets.append((m.group("fund"), int(m.group("idx")), item.strip()))
    for fund_id, idx, path in sorted(targets, key=lambda t: (t[0], -t[1])):
        fund = _fund(data, fund_id)
        rows = fund.get("holdings", [])
        if not 0 <= idx < len(rows):
            raise ReviewError(f"{fund_id} has no row {idx}")
        del rows[idx]
        _clear_flag(fund, path)
        _renumber_flags(fund, idx)
        fund.setdefault("review_log", []).append(f"delete {path}")
        log.append(f"delete {path}")
    return log


def _renumber_flags(fund: dict, deleted: int) -> None:
    """Rows after a deleted one move up by one; so do their flags."""
    def shift(flag: str) -> str:
        m = re.match(r"^(.+?\.holdings\[)(\d+)(\].*)$", flag)
        if m and int(m.group(2)) > deleted:
            return f"{m.group(1)}{int(m.group(2)) - 1}{m.group(3)}"
        return flag
    fund["review_flags"] = [shift(f) for f in fund.get("review_flags") or []]


def _clear_flag(fund: dict, path: str) -> None:
    flags = fund.get("review_flags") or []
    base = path.split(".")[0] + "." + path.split(".", 1)[1].split(".")[0] if "." in path else path
    fund["review_flags"] = [f for f in flags if f not in (path, base)
                            and not path.startswith(f + ".")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply Stage 1a review corrections")
    ap.add_argument("--holdings", help="holdings.json (default: <work dir>/holdings.json)")
    ap.add_argument("--set", action="append", default=[], metavar="PATH=VALUE")
    ap.add_argument("--delete", action="append", default=[], metavar="F3.holdings[7]")
    args = ap.parse_args()
    if not args.set and not args.delete:
        ap.error("nothing to apply: give --set and/or --delete")

    path = Path(args.holdings) if args.holdings else work_dir() / "holdings.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    try:
        log = apply(data, args.set, args.delete)
    except ReviewError as e:
        print(f"ERROR: {e} — nothing was changed", file=sys.stderr)
        return 1
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    remaining = sum(len(f.get("review_flags") or []) for f in data.get("funds", []))
    print(f"Applied {len(log)} correction(s) to {path}; {remaining} review flag(s) remain")
    for line in log:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
