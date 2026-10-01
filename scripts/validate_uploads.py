"""
Stage 0: Validate uploaded fund prospectus PDFs + SEC EDGAR email gate (B1).

Input (v0.4 C2): a directory of PDFs, or ONE .zip of them. On claude.ai the user
uploads a single .zip — PDFs uploaded one by one are placed into the
conversation context, where every page costs tokens; an archive is not, so the
scripts read the PDFs and no PDF is ever read into the conversation. A .zip is
extracted to <uploads>/extracted (paths.py). It is rejected outright — nothing
is written — if it contains a nested archive, a member that would land outside
the extraction directory (path traversal), two PDFs with the same file name,
or an oversized member. macOS metadata (__MACOSX/, ._*) is ignored and other
non-PDF members are skipped and listed.

Checks:
  1. Count of .pdf files in [7, 11] inclusive (--max-files raises the upper
     bound for measurement runs only; DEC-7 keeps 11 as the default).
  2. Each PDF opens with pypdf and yields >= 1 page of extractable text.
  3. Each PDF contains at least one holdings keyword.
  4. Each PDF contains a date pattern likely to be the asof date.
  5. A usable SEC EDGAR contact email is supplied (B1). SEC requires a contact
     email in the EDGAR request header; omitting it causes 403 Forbidden, so the
     skill cannot fetch fundamentals without one. The email is placed ONLY into
     the SEC request header and is not stored or transmitted anywhere else.

Advisory (v0.32 G3, NOT a check):
  6. Regional-fund pre-warning. A pure Asia/Europe/Japan/China regional fund is
     rejected only at Stage 1c — after the Stage 1a full-document LLM parse, the
     most expensive step in the pipeline. The fund's title usually predicts that
     outcome, so a title match raises an advisory here. It is deliberately
     NON-BLOCKING: it does not halt, does not reject, does not enter `errors`,
     and does not change the exit code or the file-count logic. A "Global
     Asia-Pacific ex-Japan" fund can legitimately hold enough US equity, and a
     keyword is not evidence — Stage 1c remains the sole authority on rejection.
     A false advisory costs one sentence of noise; a false rejection would
     discard a valid input.

Exits with code 0 on success, non-zero with an educational message on failure.

Usage:
  validate_uploads.py <upload_dir | uploads.zip> [--email you@example.com]
                      [--out result.json] [--max-files N] [--extract-to DIR]
The email may also be supplied via the EDGAR_CONTACT_EMAIL environment variable.
`--out` writes this script's JSON result so Stage 1e can reproduce the Stage 0
advisories inside the consolidated input-review block (G4).
"""

import argparse
import os
import sys
import re
import json
import zipfile
from pathlib import Path, PurePosixPath

try:
    from pypdf import PdfReader
except ImportError:
    print("ERROR: pypdf not installed. Run: pip install pypdf --break-system-packages", file=sys.stderr)
    sys.exit(2)

MIN_FILES = 7
MAX_FILES = 11

# --- v0.4 C2: .zip intake -------------------------------------------------------
_ARCHIVE_SUFFIXES = (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".zipx")
# Operational guards against a decompression bomb; no effect on any result.
_MAX_MEMBER_BYTES = 200 * 1024 * 1024
_MAX_TOTAL_BYTES = 1024 * 1024 * 1024


class IntakeError(ValueError):
    """The upload cannot be used as given; the message says why."""


def _is_metadata(parts: tuple[str, ...]) -> bool:
    name = parts[-1] if parts else ""
    return (bool(parts) and parts[0] == "__MACOSX") or name.startswith("._") \
        or name in (".DS_Store", "Thumbs.db")


def extract_zip(zip_path: Path, dest: Path) -> dict:
    """Extract the PDFs of one .zip into `dest`, flattened. Raises IntakeError.

    Every member is checked before anything is written, so a rejected archive
    leaves nothing behind. Returns {"pdfs": [names], "skipped": [members]}.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise IntakeError(f"'{zip_path.name}' is not a readable .zip archive ({e}).")
    with zf:
        plan: list[tuple[zipfile.ZipInfo, str]] = []
        skipped: list[str] = []
        seen: dict[str, str] = {}
        total = 0
        for info in zf.infolist():
            raw = info.filename
            if info.is_dir():
                continue
            norm = raw.replace("\\", "/")
            parts = PurePosixPath(norm).parts
            if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in parts:
                raise IntakeError(
                    f"'{zip_path.name}' contains '{raw}', which points outside the "
                    "archive (path traversal). Re-create the .zip from the PDF files "
                    "themselves.")
            if _is_metadata(parts):
                continue
            lower = norm.lower()
            if lower.endswith(_ARCHIVE_SUFFIXES):
                raise IntakeError(
                    f"'{zip_path.name}' contains another archive ('{raw}'). Put the "
                    "PDFs directly into one .zip — no archives inside it.")
            if not lower.endswith(".pdf"):
                skipped.append(raw)
                continue
            if info.file_size > _MAX_MEMBER_BYTES:
                raise IntakeError(f"'{raw}' is larger than {_MAX_MEMBER_BYTES // 2**20} MB "
                                  "uncompressed; a fund factsheet never is.")
            total += info.file_size
            if total > _MAX_TOTAL_BYTES:
                raise IntakeError(f"'{zip_path.name}' expands beyond "
                                  f"{_MAX_TOTAL_BYTES // 2**30} GB.")
            base = parts[-1]
            if base.lower() in seen:
                raise IntakeError(
                    f"'{zip_path.name}' holds two PDFs named '{base}' ('{seen[base.lower()]}' "
                    f"and '{raw}'). Rename one so every factsheet has its own name.")
            seen[base.lower()] = raw
            plan.append((info, base))

        dest.mkdir(parents=True, exist_ok=True)
        for stale in dest.glob("*.pdf"):        # a previous run's extraction
            stale.unlink()
        for info, base in plan:
            written = 0
            with zf.open(info) as src, open(dest / base, "wb") as out:
                while chunk := src.read(1 << 20):
                    written += len(chunk)
                    if written > _MAX_MEMBER_BYTES:
                        raise IntakeError(f"'{info.filename}' expands beyond its stated size.")
                    out.write(chunk)
    return {"pdfs": sorted(b for _, b in plan), "skipped": skipped}


def prepare_input(upload: Path, extract_to: Path | None = None) -> tuple[Path, dict]:
    """(directory holding the PDFs, input description) for a dir or a .zip."""
    if upload.is_dir():
        return upload, {"kind": "directory", "path": str(upload), "pdf_dir": str(upload),
                        "skipped": []}
    if upload.is_file() and upload.suffix.lower() == ".zip":
        if extract_to is None:
            from paths import uploads_dir, work_dir
            extract_to = uploads_dir() / "extracted"
            try:
                extract_to.mkdir(parents=True, exist_ok=True)
            except OSError:
                # A read-only uploads mount: extract next to the work files.
                extract_to = work_dir() / "uploads_extracted"
        result = extract_zip(upload, extract_to)
        return extract_to, {"kind": "zip", "path": str(upload), "pdf_dir": str(extract_to),
                            "skipped": result["skipped"]}
    raise IntakeError(
        f"'{upload}' is neither a directory nor a .zip file. Upload ONE .zip containing "
        f"{MIN_FILES}-{MAX_FILES} fund factsheet PDFs.")

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

# --- G3: regional-fund advisory markers --------------------------------------
# Matched against the fund's TITLE only — not the page, and not the sampled
# text. Almost every global factsheet carries a geographic-exposure line on page
# one ("Asia ex-Japan 4%  Europe 11%  Japan 3%"), so a looser scan fires on every
# upload and the advisory becomes noise. The title is recovered by taking the
# first few lines of page one and keeping those that read like a fund name:
# they carry a fund-type word and no percentage figure (a percentage means the
# line is data, not a name).
_TITLE_MAX_LINES = 12          # how far down page one a title may plausibly sit
_TITLE_MAX_LINE_CHARS = 150    # longer than this is merged body text, not a name

_FUND_TYPE_RE = re.compile(
    r"\b(?:funds?|portfolios?|trust|sicav|oeic|ucits|strategy|sub-?fund)\b"
    r"|基金|組合|组合",
    re.IGNORECASE,
)


def _title_text(first_page_text: str) -> str:
    """Best-effort recovery of the fund name from page one (G3)."""
    lines = [
        ln.strip() for ln in (first_page_text or "").splitlines() if ln.strip()
    ][:_TITLE_MAX_LINES]
    candidates = [
        ln for ln in lines
        if len(ln) <= _TITLE_MAX_LINE_CHARS and "%" not in ln
    ]
    titled = [ln for ln in candidates if _FUND_TYPE_RE.search(ln)]
    if titled:
        return "\n".join(titled)
    # No conventionally-titled line: fall back to the first plausible line only.
    return candidates[0] if candidates else ""

_REGIONAL_PATTERNS = [
    r"asian?",                       # Asia, Asian, Asia-Pacific
    r"pacific",
    r"europe(?:an)?",
    r"japan(?:ese)?",
    r"chin(?:a|ese)",
    r"greater\s+china",
    r"emerging\s+markets?",
    r"latin\s+america",
    r"indian?",
    r"asean",
]
_REGIONAL_RE = re.compile(
    r"\b(?:" + "|".join(_REGIONAL_PATTERNS) + r")\b", re.IGNORECASE
)

# "EM" is a regional marker only as a standalone upper-case token; lower-cased
# it collides with ordinary text, so this one pattern is case-sensitive.
_EM_RE = re.compile(r"\bEM\b")

# Bilingual HK factsheets title themselves in Chinese as often as in English.
_REGIONAL_CJK = [
    "亞洲", "亚洲", "亞太", "亚太", "歐洲", "欧洲", "日本",
    "中國", "中国", "大中華", "大中华", "新興市場", "新兴市场",
    "拉丁美洲", "印度", "東協", "东盟",
]


def regional_markers(title_text: str) -> list[str]:
    """Return the distinct regional markers found in a fund's title area (G3).

    A non-empty result is advisory, never a verdict — see the module docstring.
    """
    if not title_text:
        return []
    found = {m.group(0).lower() for m in _REGIONAL_RE.finditer(title_text)}
    if _EM_RE.search(title_text):
        found.add("EM")
    found.update(cjk for cjk in _REGIONAL_CJK if cjk in title_text)
    return sorted(found)


def regional_advisory(filename: str, markers: list[str]) -> str:
    """The advisory sentence. Names the file so the user knows which upload."""
    return (
        f"ADVISORY — '{filename}': the title mentions {', '.join(markers)}. "
        "A regional fund may hold fewer than 5 US-listed equities (or less than "
        "20% of AUM in them) and could be rejected at Stage 1c; consider "
        "substituting a global or US-focused fund. This is advisory only — the "
        "run continues and Stage 1c decides."
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


def validate(upload_dir: Path, email: str | None = None, max_files: int = MAX_FILES,
             extract_to: Path | None = None) -> dict:
    errors = []
    try:
        upload_dir, intake = prepare_input(Path(upload_dir), extract_to)
    except IntakeError as e:
        return {"ok": False, "n_files": 0, "email_ok": valid_email(email),
                "errors": [str(e)], "advisories": [], "files": [], "guidance": _GUIDANCE,
                "input": {"kind": "rejected", "path": str(upload_dir), "pdf_dir": None,
                          "skipped": []}}

    # macOS writes ._name.pdf resource forks on some volumes; they are not PDFs.
    pdfs = sorted(p for p in upload_dir.glob("*.pdf") if not p.name.startswith("._"))
    n = len(pdfs)

    # B1: email gate — checked alongside the PDF requirements.
    email_ok = valid_email(email)
    if not email_ok:
        errors.append(EMAIL_GATE_MESSAGE)

    if n < MIN_FILES or n > max_files:
        errors.append(
            f"Got {n} PDF(s); need {MIN_FILES}–{max_files}. "
            f"Please put between {MIN_FILES} and {max_files} fund factsheet PDFs into one "
            ".zip and upload it."
        )

    file_status = []
    advisories = []
    for pdf in pdfs:
        entry = {
            "file": pdf.name,
            "pages": 0,
            "looks_like_fund": False,
            "has_date": False,
            "regional_markers": [],
            "error": None,
        }
        try:
            reader = PdfReader(str(pdf))
            entry["pages"] = len(reader.pages)
            if entry["pages"] < 1:
                entry["error"] = "no_pages"
            else:
                sample = ""
                first_page = ""
                for i, page in enumerate(reader.pages[:10]):
                    try:
                        page_text = page.extract_text() or ""
                    except Exception:
                        page_text = ""
                    if i == 0:
                        first_page = page_text
                    sample += page_text

                if not sample.strip():
                    entry["error"] = "empty_text_extraction"
                else:
                    entry["looks_like_fund"] = _looks_like_fund_pdf(sample)
                    entry["has_date"] = _has_date_pattern(sample)
                    # G3: fund title only, and never promoted into `errors`.
                    entry["regional_markers"] = regional_markers(
                        _title_text(first_page)
                    )

                    if not entry["looks_like_fund"]:
                        entry["error"] = "no_holdings_keywords"
        except Exception as e:
            entry["error"] = f"parse_failed: {str(e)[:80]}"

        file_status.append(entry)

        if entry["regional_markers"]:
            advisories.append(
                regional_advisory(pdf.name, entry["regional_markers"])
            )

        if entry["error"]:
            msg = f"File '{pdf.name}': {entry['error']}."
            if entry["error"] in ("no_holdings_keywords", "empty_text_extraction"):
                msg += f" {_GUIDANCE}"
            errors.append(msg)

    return {
        # `ok` and the exit code depend on `errors` alone. Advisories are
        # deliberately excluded from both (G3).
        "ok": len(errors) == 0,
        "n_files": n,
        "email_ok": email_ok,
        "errors": errors,
        "advisories": advisories,
        "files": file_status,
        "guidance": _GUIDANCE,
        "input": intake,
    }


def main():
    ap = argparse.ArgumentParser(description="Stage 0 validation + EDGAR email gate")
    ap.add_argument("upload_dir", help="Directory of the fund PDFs, or ONE .zip of them")
    ap.add_argument(
        "--email",
        default=os.environ.get("EDGAR_CONTACT_EMAIL"),
        help="SEC EDGAR contact email (B1). Falls back to EDGAR_CONTACT_EMAIL.",
    )
    ap.add_argument(
        "--out",
        help="Optional path to write the JSON result (v0.32 G4). Stage 1e reads "
             "it via --stage0 to reproduce Stage 0 advisories in the input review.",
    )
    ap.add_argument("--max-files", type=int, default=MAX_FILES,
                    help=f"Upper bound on the PDF count (default {MAX_FILES}). For "
                         "measurement runs only (DEC-7).")
    ap.add_argument("--extract-to", help="Where a .zip is extracted (default: "
                                         "<uploads>/extracted, see paths.py).")
    args = ap.parse_args()

    upload_dir = Path(args.upload_dir)
    if not upload_dir.exists():
        print(f"ERROR: {upload_dir} does not exist", file=sys.stderr)
        sys.exit(2)

    result = validate(upload_dir, email=args.email, max_files=args.max_files,
                      extract_to=Path(args.extract_to) if args.extract_to else None)

    # G3: advisories go to stderr so they are visible without disturbing the
    # JSON contract on stdout. They never affect `ok` or the exit code.
    for advisory in result["advisories"]:
        print(advisory, file=sys.stderr)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
