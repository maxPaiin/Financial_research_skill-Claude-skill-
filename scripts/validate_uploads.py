"""
Stage 0: Validate uploaded fund prospectus PDFs.

Checks:
  1. Count of .pdf files in [7, 11] inclusive of 7, exclusive of 12.
  2. Each PDF opens with pypdf and yields >= 1 page of extractable text.
  3. Each PDF mentions at least one of the holdings keywords.

Exits with code 0 on success, non-zero with a clear message on failure.
"""

import sys
import json
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf not installed. Run: pip install pypdf --break-system-packages", file=sys.stderr)
    sys.exit(2)

MIN_FILES = 7
MAX_FILES = 11   # inclusive (i.e., < 12)

HOLDINGS_KEYWORDS = [
    "holdings", "portfolio", "holdings list",
    "持倉", "持股", "投資組合", "投资组合",
    "top 10", "top ten",
]


def looks_like_fund_pdf(text: str) -> bool:
    """Return True if the extracted text contains any holdings keyword."""
    lower = text.lower()
    for kw in HOLDINGS_KEYWORDS:
        if kw in lower:
            return True
    return False


def validate(upload_dir: Path) -> dict:
    """Return a dict {ok, errors, files}."""
    pdfs = sorted(upload_dir.glob("*.pdf"))
    n = len(pdfs)
    errors = []

    if n < MIN_FILES:
        errors.append(
            f"Got {n} PDF(s); need {MIN_FILES}-{MAX_FILES}. "
            f"收到 {n} 份,須為 {MIN_FILES}-{MAX_FILES} 份。"
        )
    elif n > MAX_FILES:
        errors.append(
            f"Got {n} PDF(s); need {MIN_FILES}-{MAX_FILES}. "
            f"收到 {n} 份,須為 {MIN_FILES}-{MAX_FILES} 份。"
        )

    file_status = []
    for pdf in pdfs:
        entry = {"file": pdf.name, "pages": 0, "looks_like_fund": False, "error": None}
        try:
            reader = PdfReader(str(pdf))
            entry["pages"] = len(reader.pages)
            if entry["pages"] < 1:
                entry["error"] = "no_pages"
            else:
                # Sample first 5 pages of text
                sample = ""
                for page in reader.pages[:5]:
                    try:
                        sample += page.extract_text() or ""
                    except Exception:
                        pass
                entry["looks_like_fund"] = looks_like_fund_pdf(sample)
                if not entry["looks_like_fund"]:
                    entry["error"] = "no_holdings_keywords"
                if not sample.strip():
                    entry["error"] = "empty_text_extraction"
        except Exception as e:
            entry["error"] = f"parse_failed: {str(e)[:80]}"
        file_status.append(entry)

        if entry["error"]:
            errors.append(
                f"File {pdf.name}: {entry['error']}. "
                f"檔案 {pdf.name}: {entry['error']}。"
            )

    return {
        "ok": len(errors) == 0,
        "n_files": n,
        "errors": errors,
        "files": file_status,
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