"""
US-only industry bucket mapping — canonical location per §5.3.

Maps raw sector/industry strings (from yfinance or SEC SIC) to one of the
standardized buckets used throughout the pipeline. All keys are lower-case
for case-insensitive matching.

v0.31 (E2.3) also carries the industry -> sector-ETF column used by the
coherence overlay's divergence detector. The ETF is only ever used to measure
*relative strength versus SPY*; it is context, never confirmation.
"""

# Canonical bucket list — do not add buckets without updating downstream.
BUCKETS = [
    "technology",
    "healthcare",
    "financials",
    "consumer_discretionary",
    "consumer_staples",
    "industrials",
    "energy",
    "materials",
    "real_estate",
    "utilities",
    "communication_services",
    "other",
]

# Mapping from raw strings → canonical bucket.
# Covers yfinance sector/industry labels and common SEC SIC descriptions.
_RAW_TO_BUCKET: dict[str, str] = {
    # Technology
    "technology": "technology",
    "information technology": "technology",
    "software": "technology",
    "semiconductors": "technology",
    "semiconductor equipment": "technology",
    "hardware": "technology",
    "electronic equipment": "technology",
    "internet": "technology",
    "it services": "technology",
    "data processing": "technology",

    # Healthcare
    "healthcare": "healthcare",
    "health care": "healthcare",
    "biotechnology": "healthcare",
    "pharmaceuticals": "healthcare",
    "medical devices": "healthcare",
    "life sciences tools": "healthcare",
    "managed health care": "healthcare",

    # Financials
    "financials": "financials",
    "financial services": "financials",
    "banks": "financials",
    "insurance": "financials",
    "capital markets": "financials",
    "diversified financials": "financials",
    "asset management": "financials",

    # Consumer Discretionary
    "consumer discretionary": "consumer_discretionary",
    "retail": "consumer_discretionary",
    "automobiles": "consumer_discretionary",
    "hotels restaurants leisure": "consumer_discretionary",
    "textiles apparel": "consumer_discretionary",
    "media": "consumer_discretionary",

    # Consumer Staples
    "consumer staples": "consumer_staples",
    "food beverage tobacco": "consumer_staples",
    "household products": "consumer_staples",
    "personal products": "consumer_staples",

    # Industrials
    "industrials": "industrials",
    "aerospace defense": "industrials",
    "machinery": "industrials",
    "transportation": "industrials",
    "commercial services": "industrials",

    # Energy
    "energy": "energy",
    "oil gas": "energy",
    "oil & gas": "energy",

    # Materials
    "materials": "materials",
    "basic materials": "materials",
    "chemicals": "materials",
    "metals mining": "materials",

    # Real Estate
    "real estate": "real_estate",
    "reits": "real_estate",

    # Utilities
    "utilities": "utilities",
    "electric utilities": "utilities",

    # Communication Services
    "communication services": "communication_services",
    "telecom": "communication_services",
    "telecommunications": "communication_services",
    "media entertainment": "communication_services",
}



# --- v0.31 (E2.3): industry -> sector-ETF column ----------------------------
#
# The overlay measures a sector's *relative strength versus SPY*, so the
# benchmark is a constant here rather than a per-bucket choice. `other` is
# deliberately left unmapped: a stock whose industry did not resolve must
# surface as "insufficient data" (E3.2), never be silently attached to a
# plausible-looking sector ETF.
BENCHMARK_ETF = "SPY"

SECTOR_ETF: dict[str, str | None] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financials": "XLF",
    "consumer_discretionary": "XLY",
    "consumer_staples": "XLP",
    "industrials": "XLI",
    "energy": "XLE",
    "materials": "XLB",
    "real_estate": "XLRE",
    "utilities": "XLU",
    "communication_services": "XLC",
    "other": None,
}


def normalize(raw: str | None) -> str:
    """Map a raw sector/industry string to a canonical bucket."""
    if not raw:
        return "other"
    key = raw.lower().strip()
    return _RAW_TO_BUCKET.get(key, "other")


def sector_etf(bucket: str | None) -> str | None:
    """Sector ETF proxy for a canonical bucket, or None when unmapped (E2.3).

    None is a meaningful answer — the caller must record "insufficient data"
    rather than fall back to a broad-market proxy, which would silently turn a
    missing mapping into a coherence verdict.
    """
    if not bucket:
        return None
    return SECTOR_ETF.get(bucket.lower().strip())
