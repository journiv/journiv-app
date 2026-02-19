"""
Unit tests for install_id generation.

Tests the CRC32 + UUIDv5 algorithm for deterministic, collision-resistant install_id generation.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

from app.core.install_id import (
    JOURNIV_NAMESPACE,
    calculate_crc,
    generate_install_id,
    generate_install_id_seed,
    validate_install_id,
)


class TestCRCCalculation:
    """Test CRC32 calculation using zlib.crc32."""

    def test_crc_basic(self):
        """Test basic CRC calculation."""
        result = calculate_crc("test")
        assert len(result) == 8
        assert result == result.lower()  # Check it's lowercase (or has no letters)
        # Verify it's valid hex
        int(result, 16)

    def test_crc_known_value(self):
        """Test CRC against a known zlib.crc32 value."""
        assert calculate_crc("test") == "d87f7e0c"

    def test_crc_deterministic(self):
        """Test that same input produces same output."""
        input_str = "4_Linux_secret_user"
        result1 = calculate_crc(input_str)
        result2 = calculate_crc(input_str)
        assert result1 == result2

    def test_crc_different_inputs(self):
        """Test that different inputs produce different outputs."""
        result1 = calculate_crc("input1")
        result2 = calculate_crc("input2")
        assert result1 != result2

    def test_crc_empty_string(self):
        """Test CRC with empty string."""
        result = calculate_crc("")
        assert len(result) == 8
        assert result == result.lower()

    def test_crc_unicode(self):
        """Test CRC with unicode characters."""
        result = calculate_crc("test_émojis_😀_中文")
        assert len(result) == 8
        assert result == result.lower()

    def test_crc_special_characters(self):
        """Test CRC with special characters."""
        result = calculate_crc("!@#$%^&*()_+-=[]{}|;:',.<>?/")
        assert len(result) == 8
        assert result == result.lower()

class TestInstallIdSeed:
    """Test seed generation for install_id."""

    @patch('app.core.install_id.os.getenv')
    @patch('app.core.install_id.platform.system')
    @patch('app.core.install_id.os.cpu_count')
    def test_seed_format(self, mock_cpu_count, mock_system, mock_getenv):
        """Test seed contains all required components in order."""
        mock_cpu_count.return_value = 4
        mock_system.return_value = 'Linux'
        mock_getenv.side_effect = lambda key, default=None: (
            'alice' if key == 'USER' else default
        )
        with patch('app.core.install_id.settings', SimpleNamespace(secret_key='secret')):
            seed = generate_install_id_seed()
        assert seed == '4_Linux_secret_alice'

    @patch('app.core.install_id.os.cpu_count')
    def test_seed_cpu_count(self, mock_cpu_count):
        """Test seed includes CPU count."""
        mock_cpu_count.return_value = 8
        seed = generate_install_id_seed()
        assert seed.startswith('8_')

    @patch('app.core.install_id.platform.system')
    def test_seed_system(self, mock_system):
        """Test seed includes system type."""
        mock_system.return_value = 'TestOS'
        seed = generate_install_id_seed()
        assert 'TestOS' in seed

    @patch('app.core.install_id.os.cpu_count')
    def test_seed_cpu_count_fallback(self, mock_cpu_count):
        """Test CPU count fallback to 1 on error."""
        mock_cpu_count.side_effect = Exception("boom")
        seed = generate_install_id_seed()
        assert seed.startswith('1_')

    @patch('app.core.install_id.os.getenv')
    def test_seed_username_fallback(self, mock_getenv):
        """Test USERNAME fallback when USER is missing."""
        def getenv_side_effect(key, default=None):
            if key == 'USER':
                return default
            if key == 'USERNAME':
                return 'bob'
            return default

        mock_getenv.side_effect = getenv_side_effect
        seed = generate_install_id_seed()
        assert seed.endswith('_bob')


class TestInstallIdGeneration:
    """Test install_id generation (UUID format)."""

    def test_generate_install_id_format(self):
        """Test generated install_id is a valid UUID."""
        install_id = generate_install_id()

        # Should be valid UUID format (36 characters)
        assert len(install_id) == 36

        # Should be parseable as UUID
        uuid_obj = uuid.UUID(install_id)
        assert uuid_obj is not None

        # Should be version 5 (name-based with SHA-1)
        assert uuid_obj.version == 5

    @patch('app.core.install_id.generate_install_id_seed')
    def test_generate_install_id_different_seeds(self, mock_seed):
        """Test that different seeds produce different InstallIds."""
        mock_seed.return_value = "4_Linux_secret1_user"
        install_id1 = generate_install_id()

        mock_seed.return_value = "4_Linux_secret2_user"
        install_id2 = generate_install_id()

        assert install_id1 != install_id2

        # Both should be valid UUIDs
        uuid.UUID(install_id1)
        uuid.UUID(install_id2)

    @patch('app.core.install_id.os.cpu_count')
    @patch('app.core.install_id.platform.system')
    def test_generate_install_id_different_systems(self, mock_system, mock_cpu):
        """Test that different systems produce different InstallIds."""
        # System 1: Linux with 4 cores
        mock_cpu.return_value = 4
        mock_system.return_value = 'Linux'
        install_id1 = generate_install_id()

        # System 2: Windows with 8 cores
        mock_cpu.return_value = 8
        mock_system.return_value = 'Windows'
        install_id2 = generate_install_id()

        # Should be different UUIDs
        assert install_id1 != install_id2
        uuid.UUID(install_id1)
        uuid.UUID(install_id2)

    def test_generate_install_id_uses_crc_and_namespace(self):
        """Test UUIDv5 uses JOURNIV_NAMESPACE with CRC output."""
        expected_uuid = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
        with patch('app.core.install_id.generate_install_id_seed', return_value='seed'):
            with patch('app.core.install_id.calculate_crc', return_value='abcd1234'):
                with patch('app.core.install_id.uuid.uuid5', return_value=expected_uuid) as mock_uuid5:
                    install_id = generate_install_id()
        mock_uuid5.assert_called_once_with(JOURNIV_NAMESPACE, 'abcd1234')
        assert install_id == str(expected_uuid)

    def test_different_secrets_different_ids(self):
        """Test that different secrets produce different UUIDs."""
        with patch('app.core.install_id.settings', SimpleNamespace(secret_key='secret1')):
            id1 = generate_install_id()
        with patch('app.core.install_id.settings', SimpleNamespace(secret_key='secret2')):
            id2 = generate_install_id()
        assert id1 != id2
        uuid.UUID(id1)
        uuid.UUID(id2)

    def test_uuid_collision_resistance(self):
        """Test that UUIDv5 provides collision resistance."""
        # Generate UUID from two similar CRC hashes
        crc1 = "abc12345"
        crc2 = "abc12346"

        uuid1 = str(uuid.uuid5(JOURNIV_NAMESPACE, crc1))
        uuid2 = str(uuid.uuid5(JOURNIV_NAMESPACE, crc2))

        # Even with similar CRCs, UUIDs should be completely different
        assert uuid1 != uuid2
        assert len(uuid1) == 36
        assert len(uuid2) == 36





class TestValidateInstallId:
    """Test InstallId validation (UUID format)."""

    def test_validate_valid_install_id(self):
        """Test validation of valid UUIDs."""
        assert validate_install_id("550e8400-e29b-41d4-a716-446655440000") is True
        assert validate_install_id("6ba7b810-9dad-11d1-80b4-00c04fd430c8") is True
        assert validate_install_id("00000000-0000-0000-0000-000000000000") is True
        # Case insensitive
        assert validate_install_id("550E8400-E29B-41D4-A716-446655440000") is True
        # No hyphens
        assert validate_install_id("550e8400e29b41d4a716446655440000") is True

    def test_validate_invalid_format(self):
        """Test validation rejects invalid UUID formats."""
        assert validate_install_id("abc") is False
        assert validate_install_id("550e8400-e29b-41d4") is False
        assert validate_install_id("") is False

    def test_validate_invalid_characters(self):
        """Test validation rejects non-hex characters."""
        assert validate_install_id("xyz12345-1234-1234-1234-123456789012") is False
        assert validate_install_id("550e8400-e29b-41d4-a716-44665544000g") is False

    def test_validate_none(self):
        """Test validation rejects None."""
        assert validate_install_id(None) is False

    def test_validate_whitespace(self):
        """Test validation rejects whitespace."""
        assert validate_install_id("550e8400-e29b-41d4-a716-446655440000 ") is False
        assert validate_install_id(" 550e8400-e29b-41d4-a716-446655440000") is False
        assert validate_install_id("550e8400 e29b-41d4-a716-446655440000") is False
