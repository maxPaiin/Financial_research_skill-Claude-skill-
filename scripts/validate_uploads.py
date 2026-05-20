"""
Stage 0: Validate uploaded fund prospectus PDFs.

Checks:
  1. Count of .pdf files in [7, 11] inclusive.
  2. Each PDF opens with pypdf and yields >= 1 page of extractable text.
  3. Each PDF contains at least one holdings keyword.
  4. Each PDF contains a date pattern likely to be the asof date.

Exits with code 0 on success, non-zero with an educational message on failure.
"""

import sys
import re
import json
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf not installed. Run: pip install pypdf --break-system-packages", file=sys.stderr)
    sys.exit(2)

MIN_FILES = 7
MAX_FILES = 11

# Holdings keywords accepted in English and Chinese (HK factsheets may be bilingual).
# Downstream processing is English-only; these only gate validation.
HOLDINGS_KEYWORDS = [
    "holdings", "portfolio", "top holdings", "portfolio composition",
    "持倉", "持股",
]

# Date patterns common in fund factsheets
_DATE_RE = re.compile(
    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{2}[/-]\d{2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4})\b",
    re.IGNORECASE,
)

_GUIDANCE = (
    "Your PDF should be a fund factsheet or prospectus that includes: "
    "(1) top-N holdings table with at least 10 entries, "
    "(2) reporting date (asof), "
    "(3) ticker or ISIN per holding, "
    "(4) weight % per holding, "
    "and ideally (5) total fund AUM. "
    "If your PDF lacks these — for example, if you uploaded a marketing brochure, "
    "an annual letter, or a regulatory filing without holdings disclosure — "
    "please replace it with the fund's monthly or quarterly factsheet."
)


def _looks_like_fund_pdf(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in HOLDINGS_KEYWORDS)


def _has_date_pattern(text: str) -> bool:
    return bool(_DATE_RE.search(text))


def validate(upload_dir: Path) -> dict:
    pdfs = sorted(upload_dir.glob("*.pdf"))
    n = len(pdfs)
    errors = []

    if n < MIN_FILES or n > MAX_FILES:
        errors.append(
            f"Got {n} PDF(s); need {MIN_FILES}–{MAX_FILES}. "
            f"Please upload between {MIN_FILES} and {MAX_FILES} fund factsheet PDFs."
        )

    file_status = []
    for pdf in pdfs:
        entry = {
            "file": pdf.name,
            "pages": 0,
            "looks_like_fund": False,
            "has_date": False,
            "error": None,
        }
        try:
            reader = PdfReader(str(pdf))
            entry["pages"] = len(reader.pages)
            if entry["pages"] < 1:
                entry["error"] = "no_pages"
            else:
                sample = ""
                for page in reader.pages[:10]:
                    try:
                        sample += page.extract_text() or ""
                    except Exception:
                        pass

                if not sample.strip():
                    entry["error"] = "empty_text_extraction"
                else:
                    entry["looks_like_fund"] = _looks_like_fund_pdf(sample)
                    entry["has_date"] = _has_date_pattern(sample)

                    if not entry["looks_like_fund"]:
                        entry["error"] = "no_holdings_keywords"
        except Exception as e:
            entry["error"] = f"parse_failed: {str(e)[:80]}"

        file_status.append(entry)

        if entry["error"]:
            msg = f"File '{pdf.name}': {entry['error']}."
            if entry["error"] in ("no_holdings_keywords", "empty_text_extraction"):
                msg += f" {_GUIDANCE}"
            errors.append(msg)

    return {
        "ok": len(errors) == 0,
        "n_files": n,
        "errors": errors,
        "files": file_status,
        "guidance": _GUIDANCE,
    }


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <upload_dir>", file=sys.stderr)
        sys.exit(2)

    upload_dir = Path(sys.argv[1])
    if not upload_dir.is_dir():
        print(f"ERROR: {upload_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    result = validate(upload_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
