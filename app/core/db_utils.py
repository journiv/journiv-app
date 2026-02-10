from __future__ import annotations

import uuid
from typing import Iterable, List


def normalize_uuid_list(values: Iterable[uuid.UUID | str] | None) -> List[uuid.UUID]:
    """Normalize UUID-like values to UUIDs for DB IN clauses."""
    if not values:
        return []
    normalized: List[uuid.UUID] = []
    for value in values:
        if isinstance(value, uuid.UUID):
            normalized.append(value)
        else:
            normalized.append(uuid.UUID(str(value)))
    return normalized
