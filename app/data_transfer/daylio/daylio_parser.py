"""
Daylio export parser.
"""
from __future__ import annotations

import base64
import json
import os
import re
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from app.core.config import settings
from app.core.logging_config import log_error, log_info, log_warning
from app.data_transfer.utils.zip_utils import prepare_extract_dir, safe_extract_zip

from .models import DaylioBackup

MAX_FILENAME_LENGTH = 255
MAX_JSON_SIZE_MB = 200
ALLOWED_EXTENSIONS = set(settings.allowed_file_extensions or []) | {".daylio", ""}


class DaylioParser:
    """
    Parser for Daylio backup exports (.daylio ZIP files).
    """

    @staticmethod
    def parse_zip(
        zip_path: Path,
        extract_to: Path,
        is_already_extracted: bool = False,
    ) -> Tuple[DaylioBackup, Path]:
        if not is_already_extracted:
            if not zip_path.exists():
                raise ValueError(f"ZIP file not found: {zip_path}")
            if not zip_path.is_file():
                raise ValueError(f"ZIP path is not a file: {zip_path}")

        try:
            if not is_already_extracted:
                prepare_extract_dir(extract_to)

            if not is_already_extracted:
                max_bytes = settings.import_export_max_file_size_mb * 1024 * 1024
                safe_extract_zip(
                    zip_path,
                    extract_to,
                    allowed_extensions=ALLOWED_EXTENSIONS,
                    max_filename_length=MAX_FILENAME_LENGTH,
                    max_total_size_bytes=max_bytes,
                )

                log_info(f"Extracted Daylio ZIP to {extract_to}", extract_path=str(extract_to))

            backup_file = extract_to / "backup.daylio"
            if not backup_file.exists():
                raise ValueError("backup.daylio not found in Daylio export")

            backup_size_mb = backup_file.stat().st_size / (1024 * 1024)
            if backup_size_mb > MAX_JSON_SIZE_MB:
                raise ValueError(
                    f"backup.daylio too large: {backup_size_mb:.1f}MB (max: {MAX_JSON_SIZE_MB}MB)"
                )

            try:
                raw_bytes = backup_file.read_bytes()
                decoded = base64.b64decode(raw_bytes)
                data = json.loads(decoded)
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Invalid Daylio backup format: {e}") from e

            if not isinstance(data, dict):
                raise ValueError("Daylio backup JSON must be an object")

            try:
                backup = DaylioBackup(**data)
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"Invalid Daylio backup schema: {e}") from e

            return backup, extract_to

        except ValueError as e:
            log_error(e, zip_path=str(zip_path))
            raise
        except zipfile.BadZipFile as e:
            log_error(e, zip_path=str(zip_path))
            raise ValueError(f"Invalid ZIP file: {e}") from e
        except Exception as e:
            log_error(e, zip_path=str(zip_path))
            raise IOError(f"Failed to parse Daylio export: {e}") from e

    @staticmethod
    def find_asset_file(assets_root: Path, checksum: str) -> Optional[Path]:
        if not checksum:
            return None
        _ = assets_root.rglob  # Keep reference; avoid globbing untrusted input.
        if not re.fullmatch(r"[a-fA-F0-9]{8,128}", checksum):
            log_warning("Invalid checksum format in Daylio asset lookup", checksum=checksum)
            return None
        candidate = assets_root.joinpath(checksum)
        if candidate.is_file():
            return candidate
        for root, _, files in os.walk(assets_root):
            if checksum in files:
                return Path(root) / checksum
        return None
