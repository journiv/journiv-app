"""
Canonical HMAC-SHA256 signing for Journiv backend -> Journiv Plus requests.

This module provides the shared signing primitive used by PlusServerClient.
It generates signatures over a canonical message format using the per-instance
secret obtained from the Journiv Plus registration handshake.

All signed requests include:
- X-Journiv-Install-ID (request header)
- X-Journiv-Timestamp (request header, replay protection)
- X-Journiv-Signature (HMAC-SHA256 over canonical message)

The signature is computed over:
- Protocol version
- HTTP method
- Request path
- Timestamp
- SHA256 hash of canonical JSON body
"""

import hashlib
import hmac
import json
from typing import Any, Dict


def generate_canonical_signature(
    *,
    method: str,
    path: str,
    timestamp: int,
    body: Dict[str, Any],
    secret: str,
) -> str:
    """
    Generate HMAC-SHA256 signature using canonical request format.

    Canonical format:
        JOURNIV-HMAC-V1
        <HTTP_METHOD>
        <PATH>
        <TIMESTAMP>
        <SHA256_HEX_OF_CANONICAL_JSON_BODY>

    This format is used for license-related and instance requests and provides:
    - Method + path binding (prevents request reuse across endpoints)
    - Body integrity (SHA256 hash of canonical JSON)
    - Timestamp for replay protection

    Args:
        method: HTTP method (e.g., "POST")
        path: Request path (e.g., "/api/v1/instance/version/check")
        timestamp: Unix timestamp in seconds
        body: Request body dictionary (will be canonicalized). Must be JSON-serializable.
        secret: Per-instance secret obtained from Journiv Plus registration

    Returns:
        Hex-encoded HMAC-SHA256 signature (64 characters)

    Raises:
        ValueError: If method or path contains newline characters, or if body contains non-JSON-serializable values

    Security Notes:
        - Uses per-instance secrets stored in the local database
        - Journiv Plus validates with constant-time comparison
        - Timestamp prevents replay attacks (validated server-side)
        - Body hash ensures request integrity
    """

    if '\n' in method or '\r' in method:
        raise ValueError(
            f"HTTP method contains invalid newline characters: {repr(method)}"
        )
    if '\n' in path or '\r' in path:
        raise ValueError(
            f"Request path contains invalid newline characters: {repr(path)}"
        )

    # Canonicalize the body: sort keys, no whitespace
    try:
        canonical_body = json.dumps(body, sort_keys=True, separators=(',', ':'))
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"request body contains non-JSON-serializable value: {str(e)}"
        ) from e

    # Compute SHA256 hash of canonical body
    body_hash = hashlib.sha256(canonical_body.encode('utf-8')).hexdigest()

    # Build canonical message
    canonical_message = f"JOURNIV-HMAC-V1\n{method}\n{path}\n{timestamp}\n{body_hash}"

    # Compute HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        canonical_message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return signature


def generate_media_signature(
    media_type: str,
    variant: str,
    media_id: str,
    user_id: str,
    expires_at: int,
    secret: str,
) -> str:
    """
    Generate a short-lived HMAC signature for media access.

    Args:
        media_type: Type of media ("journiv" or "immich")
        variant: Variant type ("original" or "thumbnail")
        media_id: Media/asset identifier
        user_id: User identifier
        expires_at: Expiration timestamp (Unix epoch seconds)
        secret: Secret key for HMAC

    Returns:
        Hex-encoded HMAC-SHA256 signature

    Raises:
        ValueError: If any parameter is empty or invalid
    """
    # Validate inputs
    if not media_type or not media_type.strip():
        raise ValueError("media_type cannot be empty")
    if not variant or not variant.strip():
        raise ValueError("variant cannot be empty")
    if not media_id or not str(media_id).strip():
        raise ValueError("media_id cannot be empty")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id cannot be empty")
    if not secret or not secret.strip():
        raise ValueError("secret cannot be empty")

    # Prevent delimiter injection - reject values containing ":" delimiter
    if ":" in media_type:
        raise ValueError("media_type cannot contain ':'")
    if ":" in variant:
        raise ValueError("variant cannot contain ':'")
    if ":" in str(media_id):
        raise ValueError("media_id cannot contain ':'")
    if ":" in str(user_id):
        raise ValueError("user_id cannot contain ':'")

    message = f"JOURNIV-MEDIA-V1:{media_type}:{variant}:{media_id}:{user_id}:{expires_at}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_media_signature(
    media_type: str,
    variant: str,
    media_id: str,
    user_id: str,
    expires_at: int,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify a media signature using constant-time comparison.

    Args:
        media_type: Type of media ("journiv" or "immich")
        variant: Variant type ("original" or "thumbnail")
        media_id: Media/asset identifier
        user_id: User identifier
        expires_at: Expiration timestamp (Unix epoch seconds)
        signature: Signature to verify
        secret: Secret key for HMAC

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        expected = generate_media_signature(
            media_type,
            variant,
            media_id,
            user_id,
            expires_at,
            secret,
        )
        return hmac.compare_digest(expected, signature)
    except (ValueError, TypeError):
        # Invalid parameters result in failed verification
        return False


def generate_export_signature(
    job_id: str,
    user_id: str,
    expires_at: int,
    secret: str,
) -> str:
    """
    Generate a short-lived HMAC signature for export download.

    Args:
        job_id: Export job identifier
        user_id: User identifier
        expires_at: Expiration timestamp (Unix epoch seconds)
        secret: Secret key for HMAC

    Returns:
        Hex-encoded HMAC-SHA256 signature
    """
    # Validate inputs
    if not job_id or not str(job_id).strip():
        raise ValueError("job_id cannot be empty")
    if not user_id or not str(user_id).strip():
        raise ValueError("user_id cannot be empty")
    if not secret or not secret.strip():
        raise ValueError("secret cannot be empty")

    # Prevent delimiter injection
    if ":" in str(job_id):
        raise ValueError("job_id cannot contain ':'")
    if ":" in str(user_id):
        raise ValueError("user_id cannot contain ':'")

    message = f"JOURNIV-EXPORT-V1:{job_id}:{user_id}:{expires_at}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_export_signature(
    job_id: str,
    user_id: str,
    expires_at: int,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify an export signature using constant-time comparison.
    """
    try:
        expected = generate_export_signature(
            job_id,
            user_id,
            expires_at,
            secret,
        )
        return hmac.compare_digest(expected, signature)
    except (ValueError, TypeError):
        return False
