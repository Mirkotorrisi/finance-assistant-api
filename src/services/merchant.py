"""Merchant identity from a messy bank description.

"PAGAMENTO POS COOP LOMBARDIA MILANO 12/03 CARTA *4821" and "COOP LOMBARDIA 0345 MILANO" are the same shop. The
merchant key keeps the first few meaningful words, so a confirmation made once ("coop lombardia" is groceries)
covers every later spelling that starts the same way, in any bank's statement.

Keep in sync with the frozen copy in migrations/versions/d4e5f6a7b8c9_add_classification_provenance.py.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Sequence

# Words banks add around the merchant name.
NOISE = frozenset({
    "pagamento", "pos", "acquisto", "carta", "addebito", "sdd", "bonifico", "operazione", "transazione", "trn",
    "ref", "rif", "payment", "purchase", "card", "contactless", "debit", "visa", "mastercard", "nfc", "pagobancomat",
})
KEY_TOKENS = 2
UNKNOWN = "unknown"


def normalize_text(description: Optional[str]) -> str:
    """Lowercase ascii words of the description without numbers, one-letter words and bank noise."""
    ascii_text = unicodedata.normalize("NFKD", description or "").encode("ascii", "ignore").decode().lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", ascii_text) if t]
    kept = [t for t in tokens if not any(c.isdigit() for c in t) and len(t) > 1 and t not in NOISE]
    return " ".join(kept)


def merchant_key(description: Optional[str]) -> str:
    words = normalize_text(description).split()
    return " ".join(words[:KEY_TOKENS]) or UNKNOWN


def rule_matches(pattern: str, description: str) -> bool:
    """A rule pattern matches the raw text (case-insensitive) or the normalised words of the description."""
    wanted = pattern.strip().lower()
    if not wanted:
        return False
    return wanted in description.lower() or wanted in normalize_text(description)


def resolve(descriptions: Sequence[str], rules: Sequence[Dict[str, str]]) -> List[Dict[str, Optional[str]]]:
    """For each description: its merchant key and the category of the most specific matching rule (or None).

    ``rules`` are ``{"pattern", "category"}`` dicts; a longer pattern wins over a shorter one.
    """
    ordered = sorted(rules, key=lambda r: -len(r["pattern"]))
    out: List[Dict[str, Optional[str]]] = []
    for description in descriptions:
        match = next((r for r in ordered if rule_matches(r["pattern"], description)), None)
        out.append({
            "description": description,
            "merchant_key": merchant_key(description),
            "category": match["category"] if match else None,
            "pattern": match["pattern"] if match else None,
        })
    return out
