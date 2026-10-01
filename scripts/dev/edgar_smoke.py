"""
Dev tool (v0.4 A0): which SEC endpoints answer, with the SEC User-Agent?

Never imported by the pipeline. The maintainer runs it once and pastes the
output into the A2 commit body, so the output deliberately never contains the
contact email — it is placed in the request header and nowhere else.

    python scripts/dev/edgar_smoke.py --email you@example.com

GETs four URLs (100 ms apart, inside SEC's fair-access rate of <= 10 req/s) and
prints the HTTP status, byte count and elapsed time of each:

  1. www.sec.gov/files/company_tickers_exchange.json   ticker -> CIK + exchange (A2)
  2. www.sec.gov/files/company_tickers.json            the documented ticker map
  3. data.sec.gov/files/company_tickers.json           the URL v0.33 built (F14)
  4. data.sec.gov/api/xbrl/companyfacts/CIK...json     one companyfacts document

Exit code 0 when all four return HTTP 200, 1 otherwise, 2 without an email.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers.edgar_provider import _USER_AGENT_APP  # noqa: E402
from validate_uploads import valid_email  # noqa: E402

URLS = [
    "https://www.sec.gov/files/company_tickers_exchange.json",
    "https://www.sec.gov/files/company_tickers.json",
    "https://data.sec.gov/files/company_tickers.json",
    # Apple Inc. — a large, long-lived 10-K filer, so the document always exists.
    "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
]

_PAUSE_S = 0.15


def probe(session: requests.Session, url: str) -> str:
    start = time.monotonic()
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        return f"ERR  {type(e).__name__:<22} {time.monotonic() - start:5.2f}s  {url}"
    elapsed = time.monotonic() - start
    return f"{resp.status_code:<4} {len(resp.content):>12,} B {elapsed:6.2f}s  {url}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", default=os.environ.get("EDGAR_CONTACT_EMAIL"),
                    help="SEC contact email for the User-Agent header only. "
                         "Falls back to EDGAR_CONTACT_EMAIL.")
    args = ap.parse_args()

    email = (args.email or "").strip()
    if not valid_email(email):
        print("A valid --email (or EDGAR_CONTACT_EMAIL) is required: SEC answers "
              "403 without a contact email in the User-Agent.", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": f"{_USER_AGENT_APP} {email}"})

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"EDGAR endpoint smoke test, {stamp}")
    print(f"User-Agent: {_USER_AGENT_APP} <contact email redacted>")
    lines = []
    for i, url in enumerate(URLS):
        if i:
            time.sleep(_PAUSE_S)
        line = probe(session, url)
        lines.append(line)
        print(line)
    ok = all(line.startswith("200 ") for line in lines)
    print("all endpoints answered 200" if ok else "at least one endpoint did not answer 200")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
