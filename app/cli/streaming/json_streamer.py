"""
Streaming JSON parser for large data.json files.

Uses ijson to parse large JSON files one object at a time,
preventing memory exhaustion on multi-GB exports.
"""
import json
from pathlib import Path
from typing import Any, Dict, Iterator

import ijson
from ijson.common import IncompleteJSONError, JSONError


def stream_parse_journiv_data(file_path: Path) -> Iterator[Dict[str, Any]]:
    """
    Stream-parse large Journiv export files.

    Yields journals one at a time instead of loading entire file into memory.

    For files < 100MB, uses standard json.load() for simplicity.
    For files >= 100MB, uses ijson streaming parser.

    Args:
        file_path: Path to data.json file

    Yields:
        Journal dictionaries one at a time

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed or ijson not available for large files
        IOError: If file read fails
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)

    # For small files (< 100MB), use standard json.load()
    if file_size_mb < 100:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                journals = data.get('journals', [])
                for journal in journals:
                    yield journal
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        except Exception as e:
            raise IOError(f"Failed to read JSON file: {e}") from e
    else:
        # For large files (>= 100MB), require ijson
        try:
            with open(file_path, 'rb') as f:
                # Parse 'journals' array items one by one
                # Using 'item' method to get complete objects
                journals = ijson.items(f, 'journals.item')
                for journal in journals:
                    yield journal
        except IncompleteJSONError as e:
            raise ValueError(f"Incomplete JSON (truncated file): {e}") from e
        except JSONError as e:
            raise ValueError(f"Invalid JSON: {e}") from e
        except Exception as e:
            raise IOError(f"Failed to stream JSON file: {e}") from e


def parse_journiv_data_standard(file_path: Path) -> Dict[str, Any]:
    """
    Standard (non-streaming) JSON parser for small files.

    Loads entire file into memory. Use only for files < 100MB.

    Args:
        file_path: Path to data.json file

    Returns:
        Parsed data dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is malformed
        IOError: If file read fails
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    except Exception as e:
        raise IOError(f"Failed to read JSON file: {e}") from e
