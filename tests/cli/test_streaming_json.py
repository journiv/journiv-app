"""
Unit tests for streaming JSON parser.

Tests the ijson-based streaming parser for large data.json files.
"""
import json
import tempfile
from pathlib import Path

import pytest

from app.cli.streaming.json_streamer import (
    parse_journiv_data_standard,
    stream_parse_journiv_data,
)


class TestStreamingJSON:
    """Test streaming JSON parser."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def small_json_file(self, temp_dir):
        """Create a small JSON file (< 100MB)."""
        json_path = temp_dir / "small_data.json"

        data = {
            "version": "1.0",
            "journals": [
                {
                    "id": "journal1",
                    "name": "My Journal",
                    "entries": [
                        {"id": "entry1", "content": "Test entry 1"},
                        {"id": "entry2", "content": "Test entry 2"},
                    ]
                },
                {
                    "id": "journal2",
                    "name": "Another Journal",
                    "entries": [
                        {"id": "entry3", "content": "Test entry 3"},
                    ]
                },
            ]
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        return json_path

    def test_stream_parse_small_file(self, small_json_file):
        """Test streaming parse on small file (uses json.load)."""
        journals = list(stream_parse_journiv_data(small_json_file))

        assert len(journals) == 2
        assert journals[0]["id"] == "journal1"
        assert journals[1]["id"] == "journal2"
        assert len(journals[0]["entries"]) == 2
        assert len(journals[1]["entries"]) == 1

    def test_stream_parse_empty_journals(self, temp_dir):
        """Test parsing file with empty journals array."""
        json_path = temp_dir / "empty.json"

        data = {
            "version": "1.0",
            "journals": []
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        journals = list(stream_parse_journiv_data(json_path))
        assert len(journals) == 0

    def test_stream_parse_missing_file(self, temp_dir):
        """Test handling of missing file."""
        missing_path = temp_dir / "missing.json"

        with pytest.raises(FileNotFoundError):
            list(stream_parse_journiv_data(missing_path))

    def test_stream_parse_invalid_json(self, temp_dir):
        """Test handling of malformed JSON."""
        json_path = temp_dir / "invalid.json"

        with open(json_path, 'w', encoding='utf-8') as f:
            f.write('{"journals": [invalid json}')

        with pytest.raises(ValueError, match="Invalid JSON"):
            list(stream_parse_journiv_data(json_path))

    def test_parse_standard(self, small_json_file):
        """Test standard (non-streaming) parser."""
        data = parse_journiv_data_standard(small_json_file)

        assert "journals" in data
        assert "version" in data
        assert len(data["journals"]) == 2

    def test_parse_standard_missing_file(self, temp_dir):
        """Test standard parser with missing file."""
        missing_path = temp_dir / "missing.json"

        with pytest.raises(FileNotFoundError):
            parse_journiv_data_standard(missing_path)

    def test_parse_standard_invalid_json(self, temp_dir):
        """Test standard parser with invalid JSON."""
        json_path = temp_dir / "invalid.json"

        with open(json_path, 'w', encoding='utf-8') as f:
            f.write('invalid json content')

        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_journiv_data_standard(json_path)

    def test_stream_parse_yields_one_at_a_time(self, small_json_file):
        """Test that streaming parser yields journals one at a time (iterator)."""
        generator = stream_parse_journiv_data(small_json_file)

        # Check it's a generator/iterator
        assert hasattr(generator, '__iter__')
        assert hasattr(generator, '__next__')

        # Get first journal
        first = next(generator)
        assert first["id"] == "journal1"

        # Get second journal
        second = next(generator)
        assert second["id"] == "journal2"

        # Should be exhausted
        with pytest.raises(StopIteration):
            next(generator)
