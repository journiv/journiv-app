"""
Stable key generation helpers for seeded/template records.
"""
import re
import unicodedata


def generate_stable_key(prefix: str, name: str) -> str:
    """
    Generate a deterministic stable key in the form ``prefix_slug_name``.
    """
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^\w\s-]", "", normalized).strip().lower()
    normalized = re.sub(r"[-\s]+", "_", normalized)
    if not normalized:
        normalized = "item"
    return f"{prefix}_{normalized}"
