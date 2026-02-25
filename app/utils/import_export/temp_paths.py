"""
Shared temporary path helpers for import/export operations.
"""
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import settings


def get_import_temp_root() -> Path:
    """Return and ensure the configured import temp root exists."""
    temp_root = Path(settings.import_temp_dir).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


@contextmanager
def import_temp_directory(*, prefix: str = "extract-") -> Iterator[Path]:
    """Create a temporary directory under the configured import temp root."""
    with tempfile.TemporaryDirectory(
        dir=str(get_import_temp_root()),
        prefix=prefix,
    ) as temp_dir:
        yield Path(temp_dir)
