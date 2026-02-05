"""
Streaming utilities for CLI operations.

Provides memory-efficient streaming for large files.
"""
from typing import Generator

__all__ = ["stream_file", "stream_lines"]

def stream_file(file_path: str, chunk_size: int = 1024 * 1024) -> Generator[bytes, None, None]:
    """
    Stream a file in chunks.

    Args:
        file_path: Path to the file
        chunk_size: Size of chunks to read

    Yields:
        Chunks of file content
    """
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

def stream_lines(file_path: str) -> Generator[str, None, None]:
    """
    Stream a file line by line.

    Args:
        file_path: Path to the file

    Yields:
        Lines from the file
    """
    with open(file_path, "r") as f:
        for line in f:
            yield line
