"""
Utilities for working with Quill Delta payloads.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional


def extract_plain_text(delta: Optional[Dict[str, Any]]) -> str:
    """Extract plain text from a Quill Delta structure."""
    if not isinstance(delta, dict):
        return ""
    ops = delta.get("ops")
    if not isinstance(ops, list):
        return ""
    parts: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        insert = op.get("insert")
        if isinstance(insert, str):
            parts.append(insert)
    return "".join(parts)


def sanitize_media_embed(embed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize media embed to ensure only one media key remains.
    Priority: image > video > audio

    Args:
        embed: Dictionary potentially containing multiple media keys

    Returns:
        Sanitized dictionary with at most one media key
    """
    if len(embed) <= 1:
        return embed

    # Check if there are multiple media keys
    media_keys = [k for k in ("image", "video", "audio") if k in embed]
    if len(media_keys) <= 1:
        return embed

    # Keep only the highest priority media key
    for key in ("image", "video", "audio"):
        if key in embed:
            return {key: embed[key]}

    return embed


def transform_delta_media(
    delta: Optional[Dict[str, Any]],
    transform_fn: Callable[[str, str], Optional[str]],
) -> Optional[Dict[str, Any]]:
    """
    Transform media references in a Quill Delta structure.

    Args:
        delta: Quill Delta structure
        transform_fn: Function that takes (media_key, media_value) and returns transformed value or None

    Returns:
        Transformed delta structure with sanitized media embeds
    """
    if not isinstance(delta, dict):
        return delta

    ops = delta.get("ops")
    if not isinstance(ops, list):
        return delta

    updated_ops: list[Dict[str, Any]] = []
    for op in ops:
        if not isinstance(op, dict):
            updated_ops.append(op)
            continue

        insert = op.get("insert")
        if isinstance(insert, dict):
            updated_insert = dict(insert)

            # Transform media references
            for key in ("image", "video", "audio"):
                value = updated_insert.get(key)
                if not isinstance(value, str):
                    continue

                transformed = transform_fn(key, value)
                if transformed is not None:
                    updated_insert[key] = transformed

            # Sanitize to ensure only one media key remains
            updated_insert = sanitize_media_embed(updated_insert)

            updated_op = dict(op)
            updated_op["insert"] = updated_insert
            updated_ops.append(updated_op)
        else:
            updated_ops.append(op)

    return {"ops": updated_ops}


def extract_media_sources(delta: Optional[Dict[str, Any]]) -> list[str]:
    """
    Extract all media source references from a Quill Delta structure.

    Args:
        delta: Quill Delta structure

    Returns:
        List of media sources (URLs, IDs, etc.) found in image/video/audio embeds
    """
    if not isinstance(delta, dict):
        return []

    ops = delta.get("ops")
    if not isinstance(ops, list):
        return []

    sources: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue

        insert = op.get("insert")
        if not isinstance(insert, dict):
            continue

        for key in ("image", "video", "audio"):
            source = insert.get(key)
            if isinstance(source, str):
                sources.append(source)

    return sources


def wrap_plain_text(text: Optional[str]) -> Dict[str, Any]:
    """Wrap plain text into a minimal Quill Delta structure.

    Ensures content ends with newline as required by Quill Delta format.
    Every valid Quill Delta must end with a trailing newline.
    """
    safe_text = text or ""
    if safe_text and not safe_text.endswith("\n"):
        safe_text = safe_text + "\n"
    return {"ops": [{"insert": safe_text}]} if safe_text else {"ops": [{"insert": "\n"}]}


def replace_media_ids(
    delta: Optional[Dict[str, Any]],
    id_map: Dict[str, str],
) -> Dict[str, Any]:
    """Replace media IDs inside image/video/audio embeds."""
    if not isinstance(delta, dict):
        return {"ops": []}

    # Validate ops structure before transformation
    ops = delta.get("ops")
    if not isinstance(ops, list):
        return {"ops": []}

    def transform_id(_key: str, value: str) -> Optional[str]:
        return id_map.get(value)

    result = transform_delta_media(delta, transform_id)
    return result if result else {"ops": []}

