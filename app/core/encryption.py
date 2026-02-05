"""
Symmetric encryption utilities for sensitive data.

This module provides Fernet-based encryption for sensitive integration tokens.
Unlike password hashing (Argon2), Fernet is reversible symmetric encryption,
allowing us to decrypt tokens when making API calls to external services.

Key Derivation:
- Uses HKDF (HMAC-based Key Derivation Function) with SHA256
- Derives a stable 32-byte Fernet key from the application's SECRET_KEY
- Key is deterministic (same SECRET_KEY → same Fernet key) to ensure tokens
  remain decryptable across app restarts

Security Notes:
- Tokens are encrypted with AES-128-CBC + HMAC-SHA256 (via Fernet)
- Encrypted data includes timestamp and signature for integrity
- Changing SECRET_KEY will invalidate all encrypted tokens (by design)
- Never log or expose decrypted tokens

Usage:
    from app.core.encryption import encrypt_token, decrypt_token

    # Encrypt a sensitive token
    encrypted = encrypt_token("user-api-key-12345")

    # Decrypt when needed (e.g., making API calls)
    original = decrypt_token(encrypted)
"""
import base64
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings
from app.core.logging_config import log_error

# Cache the derived key to avoid recomputing on every operation
_fernet_key_cache: Optional[bytes] = None


def _get_fernet_key() -> bytes:
    """
    Derive a stable Fernet key from the application's SECRET_KEY.

    Uses HKDF (HMAC-based Key Derivation Function) to convert the SECRET_KEY
    into a 32-byte key suitable for Fernet encryption.
    """
    global _fernet_key_cache

    if _fernet_key_cache is not None:
        return _fernet_key_cache

    if not settings.secret_key:
        raise ValueError(
            "SECRET_KEY must be set for encryption. "
            "Set it in your .env file or environment variables."
        )

    # Convert SECRET_KEY to bytes
    secret_bytes = settings.secret_key.encode('utf-8')

    # Use HKDF to derive a 32-byte key
    # info parameter provides domain separation (prevents key reuse in different contexts)
    kdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,  # Fernet requires exactly 32 bytes
        salt=None,  # No salt needed - SECRET_KEY is already high-entropy
        info=b'journiv-integration-token-encryption'
    )

    derived_key = kdf.derive(secret_bytes)

    # Fernet expects a URL-safe base64-encoded 32-byte key
    _fernet_key_cache = base64.urlsafe_b64encode(derived_key)

    return _fernet_key_cache


def _get_fernet() -> Fernet:
    """
    Get a Fernet instance with the derived key.

    Returns:
        Fernet: Configured Fernet instance for encryption/decryption
    """
    return Fernet(_get_fernet_key())


def encrypt_token(token: str) -> str:
    """
    Encrypt a sensitive token using Fernet symmetric encryption.

    Args:
        token: The plaintext token to encrypt (e.g., API key, OAuth token)
    """
    if not token or not token.strip():
        raise ValueError("Cannot encrypt empty token")

    try:
        fernet = _get_fernet()
        token_bytes = token.encode('utf-8')
        encrypted_bytes = fernet.encrypt(token_bytes)
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        log_error(e, action="token_encryption")
        raise


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a Fernet-encrypted token.

    Args:
        encrypted_token: The encrypted token (from encrypt_token)
    """
    if not encrypted_token or not encrypted_token.strip():
        raise ValueError("Cannot decrypt empty token")

    try:
        fernet = _get_fernet()
        encrypted_bytes = encrypted_token.encode('utf-8')
        decrypted_bytes = fernet.decrypt(encrypted_bytes)
        return decrypted_bytes.decode('utf-8')
    except InvalidToken as e:
        log_error(e, action="token_decryption")
        raise ValueError(
            "Failed to decrypt token. This may indicate the token is corrupted "
            "or the SECRET_KEY has changed. "
            "The user may need to reconnect their integration."
        ) from None
    except Exception as e:
        log_error(e, action="token_decryption")
        raise


def is_encrypted(value: str) -> bool:
    """
    Check if a string appears to be a Fernet-encrypted token.

    This is a heuristic check - it doesn't guarantee the token is valid,
    just that it has the expected format.
    """
    if not value:
        return False

    # Fernet tokens always start with "gAAAAA" (after base64 encoding)
    # This is because Fernet uses versioning (0x80) and a timestamp
    return value.startswith("gAAAAA")


def reset_key_cache():
    """
    Reset the cached Fernet key.

    This should only be called in tests or if SECRET_KEY changes at runtime.
    In production, SECRET_KEY should never change during execution.
    """
    global _fernet_key_cache
    _fernet_key_cache = None
