"""
US-only industry bucket mapping — canonical location per §5.3.

Maps raw sector/industry strings (from yfinance or SEC SIC) to one of the
standardized buckets used throughout the pipeline. All keys are lower-case
for case-insensitive matching.
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


def normalize(raw: str | None) -> str:
    """Map a raw sector/industry string to a canonical bucket."""
    if not raw:
        return "other"
    key = raw.lower().strip()
    return _RAW_TO_BUCKET.get(key, "other")
