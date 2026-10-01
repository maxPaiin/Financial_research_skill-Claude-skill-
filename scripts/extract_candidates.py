"""
Stage 1a-auto (v0.4 C3): read each factsheet with scripts, so Claude never has to.

Before v0.4, Stage 1a was Claude reading every PDF in full — the largest token
cost in a run (F17). This script reads them with pdfplumber and writes:

  candidates.json        every field with {value, confidence: high|low, page}
  candidates_summary.md  at most 15 lines per fund; missing or low-confidence
                         fields flagged with the exact apply_review.py path
  holdings.json          the draft Stage 1a record per fund (values only),
                         with `review_flags`, ready for resolve_tickers.py

Claude then reads the summary only, renders just the page of a flagged field
(render_page.py) and fixes it with apply_review.py. Nothing here is guessed:
`currency` comes from a printed currency (a bare "$" or "¥" is ambiguous and
gives null, extract_holdings.normalize_currency); `benchmark` is the printed
text or null; a field the script cannot find is null and flagged.

Fields per fund: fund_name, asof, currency, total_aum (absolute, with the unit
as printed), benchmark, fund_isin, nav_per_share, and the holdings rows
{name, ticker_raw, isin, weight} taken from the table under a holdings header —
English "Top 10 Holdings" / "Top Holdings" / "Largest Holdings" (and close
variants), Chinese 十大持倉 / 十大投資 / 主要持股 / 最大持股 (and variants). When no
ruled table is found, a text-aligned table and then plain lines under the
header are tried, at low confidence. Extend the header lists from real
factsheets only.

Usage:
  extract_candidates.py <pdf_dir> [--out-dir WORK_DIR] [--force]

--force overwrites an existing holdings.json; without it a reviewed draft
(one carrying review_log or resolution entries) is never clobbered.
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_holdings import normalize_currency  # noqa: E402
from paths import work_dir  # noqa: E402
from validate_uploads import _title_text  # noqa: E402

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None

HIGH, LOW = "high", "low"
MAX_SUMMARY_LINES = 15
MAX_ROWS = 25

HOLDINGS_HEADERS_EN = [
    r"top\s*(?:10|ten)\s+(?:holdings|positions|investments|stocks)",
    r"(?:ten\s+)?largest\s+(?:holdings|positions)", r"top\s+holdings", r"major\s+holdings",
]
HOLDINGS_HEADERS_ZH = [
    "十大持倉", "十大持仓", "十大持股", "十大投資", "十大投资", "十大投資項目", "前十大持股",
    "主要持股", "最大持股", "主要投資", "主要投资",
]
_HEADER_RE = re.compile("|".join(HOLDINGS_HEADERS_EN + [re.escape(z) for z in HOLDINGS_HEADERS_ZH]),
                        re.IGNORECASE)

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE_FORMS = [
    (re.compile(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\s+(\d{{4}})", re.I), "dmy_name"),
    (re.compile(rf"({_MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.I), "mdy_name"),
    (re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"), "ymd"),
    (re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})"), "ymd"),
    (re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})"), "dmy_num"),
    (re.compile(rf"({_MON})\s+(\d{{4}})", re.I), "my_name"),
    (re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月"), "ym"),
]
_ASOF_ANCHOR = re.compile(r"(?:as\s+(?:of|at)|data\s+as\s+(?:of|at)|valuation\s+date|"
                          r"reporting\s+date|截至|資料截至|资料截至|數據截至|数据截至|截止)", re.I)

_AMOUNT = r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_CUR = (r"(?P<cur>US\$|HK\$|USD|HKD|EUR|GBP|JPY|CNY|RMB|SGD|AUD|CHF|\$|€|£|¥|美元|港元|港幣|"
        r"歐元|日圓|日元|人民幣|英鎊)")
_UNIT = r"(?P<unit>billion|bn|b|million|mn|mil|m|thousand|k|十億|億|亿|百萬|百万|萬|万)"
_UNIT_FACTORS = {"billion": 1e9, "bn": 1e9, "b": 1e9, "十億": 1e9, "million": 1e6, "mn": 1e6,
                 "mil": 1e6, "m": 1e6, "百萬": 1e6, "百万": 1e6, "thousand": 1e3, "k": 1e3,
                 "億": 1e8, "亿": 1e8, "萬": 1e4, "万": 1e4}
_AUM_LABEL = (r"(?:total\s+fund\s+size|fund\s+size|total\s+net\s+assets|net\s+assets|"
              r"fund\s+assets|assets\s+under\s+management|\bAUM\b|基金規模|基金规模|"
              r"基金資產|基金资产|資產淨值總額|基金總值|總資產|总资产)")
_AUM_RE = re.compile(
    _AUM_LABEL + r"[^\n\d$€£¥美港歐日人英A-Z]{0,30}(?:\((?P<pcur>[^)]{1,12})\))?\s*[:：]?\s*"
    + _CUR + r"?\s*" + _AMOUNT + r"\s*" + _UNIT + r"?\b\s*(?P<cur2>USD|HKD|EUR|GBP|JPY|CNY|SGD)?",
    re.I)
_CURRENCY_LABEL_RE = re.compile(
    r"(?:base|fund|reference|reporting|dealing|share\s+class)?\s*currency\s*[:：]\s*(?P<v>[^\s,;|]+)"
    r"|(?:基本|基礎|基础|計價|计价|基金)貨幣\s*[:：]?\s*(?P<z>[^\s,;|]+)", re.I)
_BENCHMARK_RE = re.compile(
    r"(?:benchmark(?:\s+index)?|reference\s+index|comparator\s+benchmark|"
    r"基準指數|基准指数|比較基準|比较基准|參考指數|参考指数|基準|基准)\s*[:：]\s*(?P<v>[^\n]+)", re.I)
_ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
_ISIN_LABEL_RE = re.compile(r"ISIN(?:\s+code)?\s*(?:\([^)]*\))?\s*[:：]?\s*([A-Z]{2}[A-Z0-9]{9}\d)",
                            re.I)
_NAV_RE = re.compile(
    r"(?:NAV\s+per\s+(?:share|unit)|net\s+asset\s+value\s+per\s+(?:share|unit)|"
    r"每股資產淨值|每股资产净值|每單位資產淨值|每单位资产净值)\s*(?:\([^)]*\))?\s*[:：]?\s*"
    r"(?:US\$|HK\$|USD|HKD|EUR|\$|美元|港元)?\s*(\d+(?:,\d{3})*(?:\.\d+)?)", re.I)

_WEIGHT_CELL = re.compile(r"^\(?-?(\d{1,3}(?:[.,]\d+)?)\s*%?\)?$")
_TICKER_CELL = re.compile(r"^[A-Z0-9]{1,6}(?:[./-][A-Z0-9]{1,3})?(?:\s+[A-Z]{2})?(?:\s+EQUITY)?$")
_HEADER_WORDS = re.compile(r"holding|name|security|company|issuer|ticker|code|weight|%|"
                           r"名稱|名称|證券|证券|股票|代號|代号|比重|佔|占|權重|权重", re.I)
_TEXT_ROW = re.compile(
    r"^(?P<name>.*?[A-Za-z一-鿿].*?)\s+(?:(?P<ticker>[A-Z0-9]{1,6}(?:[ .][A-Z]{1,3})?)\s+)?"
    r"(?P<w>\d{1,2}(?:\.\d{1,3})?)\s*%?$")


def _field(value, confidence: str = HIGH, page: Optional[int] = None, **extra) -> dict:
    out = {"value": value, "confidence": confidence if value is not None else LOW, "page": page}
    out.update(extra)
    return out


# --- Dates ------------------------------------------------------------------------

def parse_date(text: str) -> tuple[Optional[str], bool]:
    """(ISO date, unambiguous) for the first date in `text`."""
    for regex, kind in _DATE_FORMS:
        m = regex.search(text)
        if not m:
            continue
        g = m.groups()
        try:
            if kind == "dmy_name":
                d = date(int(g[2]), _MONTHS[g[1].lower().rstrip(".")[:3]], int(g[0]))
            elif kind == "mdy_name":
                d = date(int(g[2]), _MONTHS[g[0].lower().rstrip(".")[:3]], int(g[1]))
            elif kind == "ymd":
                d = date(int(g[0]), int(g[1]), int(g[2]))
            elif kind == "dmy_num":
                a, b, y = int(g[0]), int(g[1]), int(g[2])
                if a > 12:
                    d, sure = date(y, b, a), True
                elif b > 12:
                    d, sure = date(y, a, b), True
                else:
                    d, sure = date(y, b, a), a == b   # HK convention: day first
                return d.isoformat(), sure
            elif kind == "my_name":
                y, mo = int(g[1]), _MONTHS[g[0].lower().rstrip(".")[:3]]
                d = date(y, mo, calendar.monthrange(y, mo)[1])
                return d.isoformat(), False
            else:  # ym
                y, mo = int(g[0]), int(g[1])
                d = date(y, mo, calendar.monthrange(y, mo)[1])
                return d.isoformat(), False
        except (ValueError, KeyError):
            continue
        return d.isoformat(), True
    return None, False


def find_asof(pages: list[str]) -> dict:
    for i, text in enumerate(pages, start=1):
        for m in _ASOF_ANCHOR.finditer(text):
            iso, sure = parse_date(text[m.end():m.end() + 40])
            if iso:
                return _field(iso, HIGH if sure else LOW, i)
    for i, text in enumerate(pages[:1], start=1):
        iso, _ = parse_date(text)
        if iso:
            return _field(iso, LOW, i)
    return _field(None)


# --- Key facts --------------------------------------------------------------------

def _amount(num: str, unit: Optional[str]) -> float:
    value = float(num.replace(",", ""))
    return value * _UNIT_FACTORS.get((unit or "").lower(), 1.0)


def find_aum(pages: list[str]) -> tuple[dict, Optional[str]]:
    """(total_aum field, currency printed with it)."""
    for i, text in enumerate(pages, start=1):
        m = _AUM_RE.search(text)
        if not m:
            continue
        unit = m.group("unit")
        currency = m.group("cur") or m.group("cur2") or m.group("pcur")
        value = _amount(m.group("num"), unit)
        raw = " ".join(m.group(0).split())
        return _field(value, HIGH if unit else LOW, i, unit=unit, raw=raw), currency
    return _field(None), None


def find_currency(pages: list[str], aum_currency: Optional[str], aum_page: Optional[int]) -> dict:
    """The reporting currency of total_aum: the AUM line's own currency first,
    then a labelled base currency. Never guessed; a bare $ or ¥ is null."""
    labelled, labelled_page = None, None
    for i, text in enumerate(pages, start=1):
        m = _CURRENCY_LABEL_RE.search(text)
        if m:
            labelled, labelled_page = (m.group("v") or m.group("z")), i
            break
    from_aum = normalize_currency(aum_currency) if aum_currency else None
    from_label = normalize_currency(labelled) if labelled else None
    if from_aum and from_label and from_aum != from_label:
        return _field(from_aum, LOW, aum_page, raw=aum_currency,
                      note=f"AUM printed in {from_aum}, base currency {from_label}")
    if from_aum:
        return _field(from_aum, HIGH, aum_page, raw=aum_currency)
    if from_label:
        return _field(from_label, HIGH, labelled_page, raw=labelled)
    raw = aum_currency or labelled
    return _field(None, LOW, aum_page or labelled_page, raw=raw,
                  note="ambiguous symbol" if raw else "not printed")


def find_benchmark(pages: list[str]) -> dict:
    for i, text in enumerate(pages, start=1):
        m = _BENCHMARK_RE.search(text)
        if m:
            value = m.group("v").strip().strip("|").strip()
            if value and not re.fullmatch(r"(?:n/?a|none|nil|-+|不適用|不适用)", value, re.I):
                return _field(value, HIGH if len(value) >= 6 else LOW, i)
    return _field(None, LOW, None, note="not printed")


def find_isin(pages: list[str]) -> dict:
    for i, text in enumerate(pages, start=1):
        labelled = _ISIN_LABEL_RE.findall(text)
        if labelled:
            distinct = list(dict.fromkeys(labelled))
            return _field(distinct[0], HIGH if len(distinct) == 1 else LOW, i,
                          **({"note": f"{len(distinct)} share-class ISINs"} if len(distinct) > 1 else {}))
    return _field(None, LOW, None, note="not printed")


def find_nav(pages: list[str]) -> dict:
    for i, text in enumerate(pages, start=1):
        m = _NAV_RE.search(text)
        if m:
            return _field(float(m.group(1).replace(",", "")), HIGH, i)
    return _field(None, LOW, None, note="not printed")


def find_fund_name(pages: list[str]) -> dict:
    title = _title_text(pages[0] if pages else "")
    lines = [ln for ln in title.splitlines() if ln.strip()]
    if not lines:
        return _field(None)
    from validate_uploads import _FUND_TYPE_RE
    titled = [ln for ln in lines if _FUND_TYPE_RE.search(ln)]
    return _field((titled or lines)[0].strip(), HIGH if titled else LOW, 1)


# --- Holdings ---------------------------------------------------------------------

def _clean(cell) -> str:
    return " ".join(str(cell or "").split())


def _weight_value(cell: str) -> Optional[float]:
    m = _WEIGHT_CELL.match(cell.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def rows_from_table(table: list[list]) -> list[dict]:
    """Holdings rows from a table's cells: find the weight, name, ticker and
    ISIN columns by what their cells look like, not by position."""
    rows = [[_clean(c) for c in r] for r in table if r and any(_clean(c) for c in r)]
    if not rows:
        return []
    header: list[str] = []
    if any(_HEADER_WORDS.search(c) for c in rows[0]) and not any(
            _weight_value(c) is not None for c in rows[0]):
        header, rows = rows[0], rows[1:]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    cols = list(zip(*rows))

    def share(col, test) -> float:
        return sum(1 for c in col if c and test(c)) / len(col)

    weight_scores = [share(c, lambda x: _weight_value(x) is not None) for c in cols]
    weight_col = max(range(width), key=lambda i: weight_scores[i])
    if weight_scores[weight_col] < 0.5:
        return []
    isin_scores = [share(c, lambda x: bool(_ISIN_RE.fullmatch(x))) for c in cols]
    isin_col = max(range(width), key=lambda i: isin_scores[i]) if max(isin_scores) >= 0.5 else None
    rest = [i for i in range(width) if i not in (weight_col, isin_col)]
    text_scores = {i: sum(len(c) for c in cols[i]) / len(cols[i]) for i in rest}
    name_col = max(rest, key=lambda i: text_scores[i]) if rest else None
    ticker_col = None
    for i in rest:
        if i != name_col and share(cols[i], lambda x: bool(_TICKER_CELL.match(x))) >= 0.5:
            ticker_col = i
            break

    head_w = header[weight_col] if header and weight_col < len(header) else ""
    values = [_weight_value(r[weight_col]) for r in rows]
    percent = ("%" in head_w or any("%" in r[weight_col] for r in rows)
               or any(v is not None and v > 1 for v in values)
               or bool(re.search(r"比重|佔|占|權重|权重", head_w)))
    out = []
    for r, v in zip(rows, values):
        name = r[name_col] if name_col is not None else ""
        if v is None or not name or re.fullmatch(r"(?:total|合計|合计|總計|总计)\b.*", name, re.I):
            continue
        out.append({
            "name": name,
            "ticker_raw": r[ticker_col] or None if ticker_col is not None else None,
            "isin": r[isin_col] or None if isin_col is not None else None,
            "weight": round(v / 100.0, 6) if percent else round(v, 6),
            "confidence": HIGH if percent or v <= 1 else LOW,
        })
    return out[:MAX_ROWS]


def rows_from_text(text: str) -> list[dict]:
    """Last resort: 'Name [TICKER] 7.1%' lines, at low confidence."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TEXT_ROW.match(line)
        if not m:
            if out:
                break          # the list ended
            continue
        out.append({"name": m.group("name").strip(), "ticker_raw": m.group("ticker"),
                    "isin": None, "weight": round(float(m.group("w")) / 100.0, 6),
                    "confidence": LOW})
        if len(out) >= MAX_ROWS:
            break
    return out


def find_holdings(pdf) -> dict:
    """The holdings table under the first holdings header that yields rows."""
    for page in pdf.pages:
        try:
            hits = page.search(_HEADER_RE.pattern, regex=True, case=False)
        except Exception:  # noqa: BLE001 — an unsearchable page has no header
            hits = []
        for hit in hits:
            top, bottom, x0, x1 = hit["top"], hit["bottom"], hit["x0"], hit["x1"]
            header = " ".join(hit["text"].split())
            # The table must start below the header and sit in its column: a band
            # from the header's left edge, wide enough for a short header such as
            # 十大持倉 above a centred table, narrow enough to skip the other column.
            band_l, band_r = x0 - 40, max(x1, x0 + 200) + 40
            tables = [t for t in page.find_tables()
                      if t.bbox[1] >= top - 2 and t.bbox[0] < band_r and t.bbox[2] > band_l]
            tables.sort(key=lambda t: t.bbox[1] - bottom)
            for t in tables:
                rows = rows_from_table(t.extract())
                if len(rows) >= 3:
                    return {"rows": [{**r, "page": page.page_number} for r in rows],
                            "page": page.page_number, "method": "table", "header": header}
            right = page.width if x0 > page.width * 0.45 else min(page.width,
                                                                   max(x1 + 260, page.width * 0.6))
            region = page.crop((max(0, x0 - 10), bottom, right, min(page.height, bottom + 420)))
            try:
                text_tables = region.extract_tables({"vertical_strategy": "text",
                                                     "horizontal_strategy": "text"})
            except Exception:  # noqa: BLE001
                text_tables = []
            for tbl in text_tables:
                rows = rows_from_table(tbl)
                if len(rows) >= 3:
                    return {"rows": [{**r, "confidence": LOW, "page": page.page_number}
                                     for r in rows],
                            "page": page.page_number, "method": "text-table", "header": header}
            rows = rows_from_text(region.extract_text() or "")
            if len(rows) >= 3:
                return {"rows": [{**r, "page": page.page_number} for r in rows],
                        "page": page.page_number, "method": "text-lines", "header": header}
    return {"rows": [], "page": None, "method": None, "header": None}


# --- One fund, all funds ----------------------------------------------------------

def extract_fund(pdf_path: Path, fund_id: str) -> dict:
    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
        holdings = find_holdings(pdf)
        n_pages = len(pdf.pages)
    aum, aum_currency = find_aum(pages)
    fields = {
        "fund_name": find_fund_name(pages),
        "asof": find_asof(pages),
        "currency": find_currency(pages, aum_currency, aum.get("page")),
        "total_aum": aum,
        "benchmark": find_benchmark(pages),
        "fund_isin": find_isin(pages),
        "nav_per_share": find_nav(pages),
    }
    return {"fund_id": fund_id, "file": pdf_path.name, "pages": n_pages, "fields": fields,
            "holdings": holdings, "flags": review_flags(fund_id, fields, holdings)}


_REQUIRED = ("fund_name", "asof", "currency")
_OPTIONAL_FLAGGED = ("benchmark", "total_aum")


def review_flags(fund_id: str, fields: dict, holdings: dict) -> list[dict]:
    """What Claude must look at: missing or low-confidence fields and rows."""
    flags = []
    for name in _REQUIRED + _OPTIONAL_FLAGGED:
        f = fields[name]
        if f["value"] is None or f["confidence"] == LOW:
            flags.append({"path": f"{fund_id}.{name}", "page": f.get("page"),
                          "why": f.get("note") or ("not found" if f["value"] is None
                                                   else "low confidence")})
    rows = holdings["rows"]
    if len(rows) < 5:
        flags.append({"path": f"{fund_id}.holdings", "page": holdings.get("page"),
                      "why": f"only {len(rows)} holdings rows found (need >= 5)"})
    for i, r in enumerate(rows):
        if r.get("confidence") == LOW:
            flags.append({"path": f"{fund_id}.holdings[{i}]", "page": r.get("page"),
                          "why": f"row read from {holdings.get('method')} (low confidence)"})
    total = sum(r["weight"] for r in rows if isinstance(r.get("weight"), (int, float)))
    if total > 1.0001:
        flags.append({"path": f"{fund_id}.holdings", "page": holdings.get("page"),
                      "why": f"weights sum to {total:.1%} (> 100%)"})
    return flags


def draft_record(c: dict) -> dict:
    f = c["fields"]
    return {
        "fund_id": c["fund_id"], "fund_name": f["fund_name"]["value"], "issuer": None,
        "asof": f["asof"]["value"], "currency": f["currency"]["value"],
        "total_aum": f["total_aum"]["value"], "benchmark": f["benchmark"]["value"],
        "fund_isin": f["fund_isin"]["value"], "nav_per_share": f["nav_per_share"]["value"],
        "source_file": c["file"],
        "holdings": [{k: r.get(k) for k in ("name", "ticker_raw", "isin", "weight", "page")}
                     for r in c["holdings"]["rows"]],
        "review_flags": [fl["path"] for fl in c["flags"]],
    }


def _fmt_aum(f: dict, currency: Optional[str]) -> str:
    v = f["value"]
    if v is None:
        return "n/a"
    scaled = f"{v / 1e9:.2f}bn" if v >= 1e9 else f"{v / 1e6:.0f}m" if v >= 1e6 else f"{v:,.0f}"
    return f"{scaled} {currency or '(currency?)'}"


def summary_lines(c: dict) -> list[str]:
    f = c["fields"]
    h = c["holdings"]
    rows = h["rows"]
    total = sum(r["weight"] for r in rows if isinstance(r.get("weight"), (int, float)))
    cur = f["currency"]["value"]
    nav = f["nav_per_share"]["value"]
    lines = [
        f"## {c['fund_id']} — {f['fund_name']['value'] or '(name not found)'} "
        f"({c['file']}, {c['pages']} p)",
        f"- asof {f['asof']['value'] or 'n/a'} · currency {cur or 'null'} · AUM "
        f"{_fmt_aum(f['total_aum'], cur)}" + (f" · NAV/share {nav:g}" if nav else ""),
        f"- benchmark: {f['benchmark']['value'] or 'not printed'}",
        f"- ISIN: {f['fund_isin']['value'] or 'not printed'}",
        f"- holdings: {len(rows)} rows ({h['method'] or 'none found'}"
        + (f", p{h['page']} under \"{h['header']}\"" if h["page"] else "") + f"); "
        f"weights sum {total:.1%}"
        + (f"; first: {', '.join((r.get('ticker_raw') or r['name'])[:24] for r in rows[:3])}"
           if rows else ""),
    ]
    flags = c["flags"]
    room = MAX_SUMMARY_LINES - len(lines) - 1
    if flags:
        lines.append(f"- ⚑ review {len(flags)}:")
        for fl in flags[:room]:
            lines.append(f"  - `{fl['path']}` — {fl['why']}"
                         + (f" (p{fl['page']})" if fl.get("page") else ""))
        if len(flags) > room:
            lines[-1] = (f"  - … {len(flags) - room + 1} more in candidates.json")
    else:
        lines.append("- no field flagged")
    return lines[:MAX_SUMMARY_LINES]


def extract_all(pdf_dir: Path) -> dict:
    pdfs = sorted(p for p in Path(pdf_dir).glob("*.pdf") if not p.name.startswith("._"))
    funds = [extract_fund(p, f"F{i}") for i, p in enumerate(pdfs, start=1)]
    return {"version": "0.4", "generated": date.today().isoformat(),
            "pdf_dir": str(pdf_dir), "funds": funds}


def _reviewed(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(f.get("review_log") or any("resolution" in h for h in f.get("holdings", []))
               for f in data.get("funds", []))


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 1a-auto: scripted factsheet extraction")
    ap.add_argument("pdf_dir", help="Directory of factsheet PDFs (Stage 0's input.pdf_dir)")
    ap.add_argument("--out-dir", help="Where to write (default: the work dir, paths.py)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite a holdings.json that has already been reviewed")
    args = ap.parse_args()
    if pdfplumber is None:
        print("ERROR: pdfplumber is not installed (pip install -r requirements.txt)",
              file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else work_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    holdings_path = out_dir / "holdings.json"
    if holdings_path.exists() and _reviewed(holdings_path) and not args.force:
        print(f"ERROR: {holdings_path} already carries review corrections; rerun with --force "
              "to replace it.", file=sys.stderr)
        return 1

    cands = extract_all(Path(args.pdf_dir))
    (out_dir / "candidates.json").write_text(json.dumps(cands, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    summary = ["# Stage 1a candidates — review the flagged fields only", ""]
    for c in cands["funds"]:
        summary += summary_lines(c) + [""]
    (out_dir / "candidates_summary.md").write_text("\n".join(summary), encoding="utf-8")
    holdings_path.write_text(json.dumps({"funds": [draft_record(c) for c in cands["funds"]]},
                                        indent=2, ensure_ascii=False), encoding="utf-8")
    n_flags = sum(len(c["flags"]) for c in cands["funds"])
    print(f"Extracted {len(cands['funds'])} factsheets -> {out_dir} "
          f"(candidates.json, candidates_summary.md, holdings.json); {n_flags} field(s) flagged "
          "for review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
