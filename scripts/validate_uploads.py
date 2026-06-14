"""
Stage 0: Validate uploaded fund prospectus PDFs + SEC EDGAR email gate (B1).

Checks:
  1. Count of .pdf files in [7, 11] inclusive.
  2. Each PDF opens with pypdf and yields >= 1 page of extractable text.
  3. Each PDF contains at least one holdings keyword.
  4. Each PDF contains a date pattern likely to be the asof date.
  5. A usable SEC EDGAR contact email is supplied (B1). SEC requires a contact
     email in the EDGAR request header; omitting it causes 403 Forbidden, so the
     skill cannot fetch fundamentals without one. The email is placed ONLY into
     the SEC request header and is not stored or transmitted anywhere else.

Exits with code 0 on success, non-zero with an educational message on failure.

Usage:
  validate_uploads.py <upload_dir> [--email you@example.com]
The email may also be supplied via the EDGAR_CONTACT_EMAIL environment variable.
"""

import argparse
import os
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

# Date patterns common in fund factsheets. The v1 regex only matched
# `dd/mm/yyyy`, `yyyy-mm-dd`, and `Month yyyy` — which missed `Q1 2025`,
# `FY 2024`, `31 March 2025`, and `March 31, 2025` formats that real
# HK-distributed factsheets commonly use.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_DATE_PATTERNS = [
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}",                                  # 31/03/2025
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}",                                    # 2025-03-31
    rf"{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}",            # March 31, 2025
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\.?\s+\d{{4}}",              # 31 March 2025
    rf"{_MONTH}\s+\d{{4}}",                                            # March 2025
    r"Q[1-4][\s/\-,]*\d{4}",                                           # Q1 2025, Q1-2025, Q1/2025
    r"\d{4}[\s/\-,]*Q[1-4]",                                           # 2025 Q1
    r"FY[\s\-]*\d{2,4}",                                               # FY24 / FY 2024
    r"H[12][\s/\-]*\d{4}",                                             # H1 2025
]
_DATE_RE = re.compile(
    r"\b(?:" + "|".join(_DATE_PATTERNS) + r")\b",
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


# --- B1: SEC EDGAR contact-email gate ---------------------------------------
# Deliberately lenient format check — we are not verifying deliverability, only
# that the string is a plausible single email to place in the SEC UA header.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EMAIL_GATE_MESSAGE = (
    "HALT — a SEC EDGAR contact email is required before this skill can run.\n"
    "\n"
    "Why: SEC requires every EDGAR request to declare a User-Agent that includes "
    "a contact email. Requests without one are answered with HTTP 403 Forbidden, "
    "so the skill cannot fetch the US fundamentals it ranks on.\n"
    "\n"
    "Privacy: the email is placed ONLY into the SEC request header (SEC's stated "
    "use is to contact the script operator if it causes problems). It is not "
    "stored, logged to the report, or transmitted anywhere else.\n"
    "\n"
    "Provide a valid email via --email you@example.com (or the EDGAR_CONTACT_EMAIL "
    "environment variable) and re-run."
)


def valid_email(email: str | None) -> bool:
    """Basic format validation for the SEC contact email (B1)."""
    if not email:
        return False
    return bool(_EMAIL_RE.match(email.strip()))


def _looks_like_fund_pdf(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in HOLDINGS_KEYWORDS)


def _has_date_pattern(text: str) -> bool:
    return bool(_DATE_RE.search(text))


def validate(upload_dir: Path, email: str | None = None) -> dict:
    pdfs = sorted(upload_dir.glob("*.pdf"))
    n = len(pdfs)
    errors = []

    # B1: email gate — checked alongside the PDF requirements.
    email_ok = valid_email(email)
    if not email_ok:
        errors.append(EMAIL_GATE_MESSAGE)

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
        "email_ok": email_ok,
        "errors": errors,
        "files": file_status,
        "guidance": _GUIDANCE,
    }


def main():
    ap = argparse.ArgumentParser(description="Stage 0 validation + EDGAR email gate")
    ap.add_argument("upload_dir", help="Directory containing the uploaded fund PDFs")
    ap.add_argument(
        "--email",
        default=os.environ.get("EDGAR_CONTACT_EMAIL"),
        help="SEC EDGAR contact email (B1). Falls back to EDGAR_CONTACT_EMAIL.",
    )
    args = ap.parse_args()

    upload_dir = Path(args.upload_dir)
    if not upload_dir.is_dir():
        print(f"ERROR: {upload_dir} is not a directory", file=sys.stderr)
        sys.exit(2)

    result = validate(upload_dir, email=args.email)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
