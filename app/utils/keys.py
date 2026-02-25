"""
Stable key generation helpers for seeded/template records.
"""
import hashlib
import re
import unicodedata
from typing import Optional

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


def generate_import_stable_key(prefix: str, external_id: Optional[str]) -> Optional[str]:
    """
    Generate a deterministic stable key from an external source ID.

    Keeps import IDs distinct and idempotent while respecting DB length limits.
    Returns None when external_id is missing/blank.
    """
    if not external_id:
        return None

    normalized = external_id.strip()
    if not normalized:
        return None

    candidate = f"{prefix}:{normalized}"
    if len(candidate) <= MAX_STABLE_KEY_LENGTH:
        return candidate

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    head_budget = max(0, MAX_STABLE_KEY_LENGTH - len(prefix) - len(digest) - 2)
    if head_budget <= 0 or (len(prefix) + 1 + len(digest) > MAX_STABLE_KEY_LENGTH):
        raise ValueError("Prefix is too long for import stable key generation")
    return f"{prefix}:{normalized[:head_budget]}:{digest}"
