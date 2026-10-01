"""
Render ONE page of a factsheet to a PNG (v0.4 C3) — for a targeted visual check.

When candidates_summary.md flags a field, Claude renders just the page it came
from and looks at that image — never the PDF itself, and never the whole
document. The image is small (110 dpi by default) because one field is all it
has to show.

Usage:
  render_page.py <pdf> --page N [--dpi 110] [--out PATH]

Pages are numbered from 1, as in candidates_summary.md. The default output is
<work dir>/pages/<pdf stem>_p<N>.png; the path is printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import work_dir  # noqa: E402


def render(pdf_path: Path, page: int, dpi: int = 110, out: Path | None = None) -> Path:
    import pdfplumber
    with pdfplumber.open(str(pdf_path)) as pdf:
        if not 1 <= page <= len(pdf.pages):
            raise ValueError(f"{pdf_path.name} has {len(pdf.pages)} page(s); page {page} "
                             "does not exist")
        out = out or work_dir() / "pages" / f"{pdf_path.stem}_p{page}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        pdf.pages[page - 1].to_image(resolution=dpi).save(str(out), format="PNG")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render one factsheet page to a PNG")
    ap.add_argument("pdf")
    ap.add_argument("--page", type=int, required=True, help="1-based page number")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--out", help="PNG path (default: <work dir>/pages/<stem>_p<N>.png)")
    args = ap.parse_args()
    try:
        out = render(Path(args.pdf), args.page, args.dpi, Path(args.out) if args.out else None)
    except (ValueError, OSError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
