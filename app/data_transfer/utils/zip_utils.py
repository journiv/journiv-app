"""Shared ZIP extraction utilities for data transfer imports."""
from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path
from typing import Iterable

from app.core.config import settings
from app.core.logging_config import log_error, log_warning

DEFAULT_MAX_FILES = 50000


def _ensure_within_base_dir(extract_to: Path, base_temp_dir: Path) -> None:
    try:
        if not extract_to.is_relative_to(base_temp_dir):
            log_error(
                "Extraction path outside allowed base directory",
                extract_path=str(extract_to),
                base_dir=str(base_temp_dir),
            )
            raise ValueError(
                f"Extraction path must be within {base_temp_dir}, got {extract_to}"
            )
    except AttributeError:
        try:
            extract_to.relative_to(base_temp_dir)
        except ValueError:
            log_error(
                "Extraction path outside allowed base directory",
                extract_path=str(extract_to),
                base_dir=str(base_temp_dir),
            )
            raise ValueError(
                f"Extraction path must be within {base_temp_dir}, got {extract_to}"
            ) from None


def prepare_extract_dir(extract_to: Path) -> None:
    """Validate and prepare the extraction directory."""
    base_temp_dir = Path(settings.import_temp_dir).resolve()
    extract_to_resolved = extract_to.resolve()

    root_path = Path("/")
    home_path = Path.home()
    if (extract_to_resolved == root_path or
        extract_to_resolved == home_path or
        (os.name == "nt" and len(extract_to_resolved.parts) == 1 and extract_to_resolved.drive)):
        log_error(
            "Unsafe extraction path detected",
            extract_path=str(extract_to_resolved),
        )
        raise ValueError(f"Unsafe extraction path: {extract_to_resolved}")

    _ensure_within_base_dir(extract_to_resolved, base_temp_dir)

    if extract_to.exists():
        shutil.rmtree(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)


def safe_extract_zip(
    zip_path: Path,
    extract_to: Path,
    *,
    allowed_extensions: Iterable[str],
    max_filename_length: int,
    max_total_size_bytes: int,
    max_files: int = DEFAULT_MAX_FILES,
) -> None:
    """Safely extract a ZIP file after validating entries."""
    with zipfile.ZipFile(zip_path, "r") as zipf:
        corrupt_file = zipf.testzip()
        if corrupt_file is not None:
            raise ValueError(f"ZIP file is corrupted: {corrupt_file}")

        total_size = sum(info.file_size for info in zipf.infolist())
        if total_size > max_total_size_bytes:
            raise ValueError(
                f"ZIP too large: {total_size / (1024*1024):.1f}MB "
                f"(max: {max_total_size_bytes / (1024*1024):.0f}MB)"
            )

        extract_root = extract_to.resolve()
        file_count = 0
        allowed_exts = {ext.lower() for ext in allowed_extensions}

        for info in zipf.infolist():
            file_count += 1
            if file_count > max_files:
                raise ValueError(f"ZIP contains too many files (max: {max_files})")
            if info.is_dir():
                continue
            if len(info.filename) > max_filename_length:
                raise ValueError(f"Filename too long: {info.filename[:50]}...")

            # Normalize filename by stripping leading slashes (common in Daylio exports)
            # This is safe because we still validate the path doesn't escape the extract directory
            normalized_filename = info.filename.lstrip("/")

            # Reject empty filenames after normalization
            if not normalized_filename:
                raise ValueError(f"ZIP contains invalid empty filename: {info.filename}")

            # Check for path traversal after normalization
            if ".." in normalized_filename.split("/"):
                raise ValueError(f"ZIP contains unsafe path: {info.filename}")
            if "\x00" in normalized_filename:
                raise ValueError(f"ZIP contains invalid filename: {info.filename}")

            dest_path = (extract_to / normalized_filename).resolve()
            try:
                dest_path.relative_to(extract_root)
            except ValueError:
                raise ValueError(f"ZIP contains unsafe path: {info.filename}") from None

            if info.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError(f"ZIP contains symlink: {info.filename}")

            file_ext = os.path.splitext(normalized_filename.lower())[1]
            if file_ext and file_ext not in allowed_exts:
                log_warning(
                    f"Skipping file with unsupported extension: {info.filename}",
                    filename=info.filename,
                    extension=file_ext,
                )
                continue

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            # Extract with normalized filename
            info.filename = normalized_filename
            zipf.extract(info, extract_to)
