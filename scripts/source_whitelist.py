"""
The source whitelist (v0.41): which pages may be fetched and which names may be
cited in the macro, expectations and notice stages.

`references/source_whitelist.json` lists the primary-tier institutions of the C2
gate, each with its domains (a domain may carry a path prefix, e.g.
`ec.europa.eu/eurostat`) and the aliases a citation may start with. This module
answers two questions, and nothing else:

  institution_for_url(url)       -> institution id, or None
  institution_for_citation(item) -> institution id, or None

plus `is_internal_citation(item)`: the run's own data ("Layer 2 …", "SEC EDGAR …",
"yfinance …") may be cited as evidence about a stock, needs no fetched page, and is
refused in the files `internal_refused_in()` names.

A URL matches when its host is a listed domain or a subdomain of one (so
`www.federalreserve.gov` and `fred.stlouisfed.org` match, `federalreserve.gov.example.com`
does not) and, where the entry has a path prefix, its path starts with it. A
citation item matches when it starts with an alias followed by a non-word
character or the end (so "Fed SEP 2026-09" matches, "Federalist" does not).

CLI (for Claude, during M1, M2 and H1):
  source_whitelist.py domains          one line per institution: id, aliases, domains
  source_whitelist.py check URL ...    "OK <id> <url>" or "NO <url>"; exit 1 if any NO
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

WHITELIST_PATH = Path(__file__).resolve().parents[1] / "references" / "source_whitelist.json"


class WhitelistError(ValueError):
    pass


@lru_cache(maxsize=4)
def load(path: Path = WHITELIST_PATH) -> dict[str, dict]:
    """{institution id: {"name", "aliases", "domains"}}; raises WhitelistError."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise WhitelistError(f"source whitelist unreadable ({path.name}: {e})")
    insts = data.get("institutions")
    if not isinstance(insts, dict) or not insts:
        raise WhitelistError(f"{path.name} has no 'institutions'")
    for iid, rec in insts.items():
        if not rec.get("aliases") or not rec.get("domains"):
            raise WhitelistError(f"{path.name}: '{iid}' needs at least one alias and one domain")
    return insts


def _split_domain(entry: str) -> tuple[str, str]:
    host, _, prefix = entry.strip().lower().partition("/")
    return host, prefix.strip("/")


def institution_for_url(url: str, path: Path = WHITELIST_PATH) -> Optional[str]:
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")
    url_path = parts.path or "/"
    for iid, rec in load(path).items():
        for entry in rec["domains"]:
            dom, prefix = _split_domain(entry)
            if host != dom and not host.endswith("." + dom):
                continue
            if prefix and not (url_path == "/" + prefix or url_path.startswith("/" + prefix + "/")):
                continue
            return iid
    return None


@lru_cache(maxsize=4)
def _alias_patterns(path: Path = WHITELIST_PATH) -> list[tuple[re.Pattern, str]]:
    pairs = [(alias.strip(), iid) for iid, rec in load(path).items() for alias in rec["aliases"]]
    pairs.sort(key=lambda p: -len(p[0]))          # longest alias first
    return [(re.compile(re.escape(a) + r"(?![\w-])", re.IGNORECASE), iid) for a, iid in pairs]


def institution_for_citation(item: str, path: Path = WHITELIST_PATH) -> Optional[str]:
    text = (item or "").strip()
    for pattern, iid in _alias_patterns(path):
        if pattern.match(text):
            return iid
    return None


@lru_cache(maxsize=4)
def _internal(path: Path = WHITELIST_PATH) -> tuple[list[re.Pattern], tuple[str, ...]]:
    """(alias patterns, files where internal citations are refused)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise WhitelistError(f"source whitelist unreadable ({Path(path).name}: {e})")
    internal = data.get("internal") or {}
    patterns = [re.compile(re.escape(a.strip()) + r"(?![\w-])", re.IGNORECASE)
                for a in sorted(internal.get("aliases") or [], key=len, reverse=True)]
    return patterns, tuple(internal.get("not_in") or ())


def is_internal_citation(item: str, path: Path = WHITELIST_PATH) -> bool:
    """True for the run's own data ("Layer 2 …", "SEC EDGAR …", "yfinance …")."""
    text = (item or "").strip()
    return any(p.match(text) for p in _internal(path)[0])


def internal_refused_in(path: Path = WHITELIST_PATH) -> tuple[str, ...]:
    return _internal(path)[1]


def citation_items(bracket: str) -> list[str]:
    """'[Fed SEP; BLS CPI]' -> ['Fed SEP', 'BLS CPI']; empty items dropped."""
    inner = bracket.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    return [p.strip() for p in inner.split(";") if p.strip()]


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in ("domains", "check"):
        print("usage: source_whitelist.py domains | check URL [URL ...]", file=sys.stderr)
        return 2
    insts = load()
    if args[0] == "domains":
        for iid, rec in insts.items():
            print(f"{iid}: aliases {', '.join(rec['aliases'][:4])}"
                  f"{' …' if len(rec['aliases']) > 4 else ''} | domains {', '.join(rec['domains'])}")
        return 0
    bad = 0
    for url in args[1:]:
        iid = institution_for_url(url)
        print(f"OK {iid} {url}" if iid else f"NO {url}")
        bad += iid is None
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
