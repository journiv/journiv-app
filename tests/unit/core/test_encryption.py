"""
Unit tests for Fernet token encryption/decryption.

These tests verify that the encryption module correctly encrypts and decrypts
sensitive integration tokens using Fernet symmetric encryption.
"""
import pytest

from app.core.encryption import (
    decrypt_token,
    encrypt_token,
    is_encrypted,
    reset_key_cache,
)


def make_fake_token(label: str) -> str:
    return f"FAKE_TOKEN_{label}_FOR_TESTS"  # noqa: S105


class TestEncryption:
    """Test encryption and decryption of tokens."""

    def setup_method(self):
        """Reset key cache before each test."""
        reset_key_cache()

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption are reversible."""
        original_token = make_fake_token("ROUNDTRIP")

        # Encrypt the token
        encrypted = encrypt_token(original_token)

        # Verify it's encrypted (looks different from original)
        assert encrypted != original_token
        assert len(encrypted) > len(original_token)  # Encrypted tokens are longer

        # Decrypt and verify we get the original back
        decrypted = decrypt_token(encrypted)
        assert decrypted == original_token

    def test_encrypt_different_tokens_produce_different_ciphertext(self):
        """Test that different tokens produce different encrypted output."""
        token1 = make_fake_token("ONE")
        token2 = make_fake_token("TWO")

        encrypted1 = encrypt_token(token1)
        encrypted2 = encrypt_token(token2)

        # Different tokens should produce different ciphertext
        assert encrypted1 != encrypted2

    def test_encrypt_same_token_produces_different_ciphertext(self):
        """Test that encrypting the same token twice produces different ciphertext (due to IV)."""
        token = make_fake_token("SAME")

        encrypted1 = encrypt_token(token)
        encrypted2 = encrypt_token(token)

        # Fernet includes a timestamp, so same plaintext → different ciphertext
        assert encrypted1 != encrypted2

        # But both should decrypt to the same value
        assert decrypt_token(encrypted1) == token
        assert decrypt_token(encrypted2) == token

    def test_encrypt_empty_string_raises_error(self):
        """Test that encrypting an empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot encrypt empty token"):
            encrypt_token("")

    def test_encrypt_none_raises_error(self):
        """Test that encrypting None raises error."""
        with pytest.raises((ValueError, AttributeError)):
            encrypt_token(None)

    def test_decrypt_empty_string_raises_error(self):
        """Test that decrypting an empty string raises ValueError."""
        with pytest.raises(ValueError, match="Cannot decrypt empty token"):
            decrypt_token("")

    def test_decrypt_invalid_token_raises_error(self):
        """Test that decrypting an invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Failed to decrypt token"):
            decrypt_token(make_fake_token("INVALID"))

    def test_decrypt_corrupted_token_raises_error(self):
        """Test that decrypting a corrupted Fernet token raises error."""
        # Create a valid token, then corrupt it
        encrypted = encrypt_token(make_fake_token("CORRUPT"))
        corrupted = encrypted[:-5] + "AAAAA"  # Corrupt the last 5 chars

        with pytest.raises(ValueError, match="Failed to decrypt token"):
            decrypt_token(corrupted)

    def test_is_encrypted_detects_fernet_tokens(self):
        """Test that is_encrypted correctly identifies Fernet tokens."""
        token = make_fake_token("PLAINTEXT")
        encrypted = encrypt_token(token)

        # Encrypted tokens start with "gAAAAA"
        assert is_encrypted(encrypted)
        assert not is_encrypted(token)
        assert not is_encrypted("")
        assert not is_encrypted("random-string")

    def test_encrypt_long_token(self):
        """Test that long tokens can be encrypted and decrypted."""
        long_token = "a" * 1000  # 1000 character token

        encrypted = encrypt_token(long_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == long_token

    def test_encrypt_unicode_token(self):
        """Test that Unicode tokens can be encrypted and decrypted."""
        unicode_token = "token-with-émojis-🔑-and-中文"

        encrypted = encrypt_token(unicode_token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == unicode_token

    def test_key_caching(self):
        """Test that the Fernet key is cached (performance optimization)."""
        import app.core.encryption as encryption

        # Reset cache
        reset_key_cache()
        assert encryption._fernet_key_cache is None

        # First encryption should create and cache the key
        encrypt_token(make_fake_token("CACHE_ONE"))
        assert encryption._fernet_key_cache is not None

        # Second encryption should reuse the cached key
        encrypt_token(make_fake_token("CACHE_TWO"))
        assert encryption._fernet_key_cache is not None


# ================================================================================
# Integration Tests (require settings.secret_key)
# ================================================================================

class TestEncryptionWithSettings:
    """Test encryption with actual application settings."""

    def test_encrypt_with_app_secret_key(self):
        """Test encryption using the actual SECRET_KEY from settings."""
        from app.core.config import settings

        # Verify SECRET_KEY is set
        assert settings.secret_key

        # Encrypt and decrypt with the app's SECRET_KEY
        token = make_fake_token("APP_SECRET")
        encrypted = encrypt_token(token)
        decrypted = decrypt_token(encrypted)

        assert decrypted == token

    def test_deterministic_key_derivation(self):
        """Test that the same SECRET_KEY always produces the same Fernet key."""
        from app.core.encryption import _get_fernet_key

        # Get key twice
        key1 = _get_fernet_key()
        key2 = _get_fernet_key()

        # Should be identical (deterministic)
        assert key1 == key2
