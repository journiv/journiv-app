"""
Stable key generation helpers for seeded/template records.
"""
import re
import unicodedata

MAX_STABLE_KEY_LENGTH = 100


def generate_stable_key(prefix: str, name: str) -> str:
    """
    Generate a deterministic stable key in the form ``prefix_slug_name``.
    """
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    normalized = re.sub(r"[-\s]+", "_", normalized)
    if not normalized:
        normalized = "item"

    allowed = MAX_STABLE_KEY_LENGTH - (len(prefix) + 1)
    if allowed <= 0:
        raise ValueError("Prefix is too long for stable key generation")

    normalized = normalized[:allowed]
    if not normalized:
        normalized = "item"[:allowed]
        if not normalized:
            raise ValueError("Unable to generate stable key with the provided prefix")

    return f"{prefix}_{normalized}"
