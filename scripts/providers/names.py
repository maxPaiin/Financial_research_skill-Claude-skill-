"""
Company-name normalisation for name-only holdings rows (v0.4 A2 / A6).

Factsheets — Chinese-language ones especially — often list a holding by name
alone. Matching that name against SEC's issuer names needs both sides in one
form: casefolded, punctuation stripped, and corporate-form words dropped, so
"Taiwan Semiconductor Manufacturing Company Limited", "TAIWAN SEMICONDUCTOR
MANUFACTURING CO LTD" and "Taiwan Semiconductor Manufacturing ADR" all reduce to
"taiwan semiconductor manufacturing".

Normalisation only decides which SEC row a name refers to. Whether the fund
holds the US line or the home-market line is a separate question, answered by
the row's ISIN and ADR marker in `resolve_tickers.py` — never by the name alone.
"""

from __future__ import annotations

import re
import unicodedata

# Corporate-form tokens (A6). The long forms of the listed abbreviations
# (company, limited, incorporated) and "the" are included so a factsheet's full
# legal name meets SEC's abbreviated one.
_DROP_TOKENS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "plc", "holding", "holdings", "group", "sa", "nv", "se", "ag",
    "sponsored", "ads", "adr", "the",
}
_DROP_PHRASES = (
    "american depositary shares", "american depositary share",
    "american depositary receipts", "american depositary receipt",
    "ordinary shares", "common stock",
    "class a", "class b", "class c",
)
# zh-Hant / zh-Hans corporate-form suffixes, stripped from the end of a name.
_CJK_SUFFIXES = (
    "股份有限公司", "有限公司", "控股公司", "控股", "集團", "集团", "公司",
)

# Apostrophes are removed outright, so "McDonald's" meets SEC's "MCDONALDS".
_APOSTROPHES = re.compile(r"['’]")
# Abbreviation dots are removed ("Inc." -> "inc", "S.A." -> "sa", "U.S." -> "us");
# a dot inside a word separates it ("Amazon.com" -> "amazon com", as SEC writes it).
_TRAILING_DOT = re.compile(r"\.(?=\s|$)")
_INITIALS_DOT = re.compile(r"(?<=\b\w)\.(?=\w\b)")
# Any other punctuation separates words ("AT&T" -> "at t", "Coca-Cola" -> "coca cola").
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize_company_name(raw: str | None) -> str:
    """Matching key for a company name; "" when nothing meaningful is left."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", str(raw)).casefold()
    s = _APOSTROPHES.sub("", s)
    s = _TRAILING_DOT.sub("", s)
    while _INITIALS_DOT.search(s):
        s = _INITIALS_DOT.sub("", s)
    s = _PUNCT.sub(" ", s).replace("_", " ")
    s = " " + _SPACES.sub(" ", s).strip() + " "
    for phrase in _DROP_PHRASES:
        s = s.replace(f" {phrase} ", " ")
    # A bare share-class letter right after a corporate-form word ("Mastercard
    # Inc A", "Berkshire Hathaway Inc B") carries no issuer identity and is
    # dropped with it; "AT&T" keeps its "t".
    words: list[str] = []
    prev_dropped = False
    for w in s.split():
        if w in _DROP_TOKENS or (prev_dropped and len(w) == 1 and w.isalpha()):
            prev_dropped = w in _DROP_TOKENS
            continue
        words.append(w)
        prev_dropped = False
    out = " ".join(words)
    stripped = True
    while stripped:
        stripped = False
        for suffix in _CJK_SUFFIXES:
            if out.endswith(suffix) and len(out) > len(suffix):
                out = out[: -len(suffix)].rstrip()
                stripped = True
    return out
