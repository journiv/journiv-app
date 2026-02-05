"""
CLI logging utilities.

Dual logging strategy:
- Console: Clean, user-friendly output (INFO by default, DEBUG when verbose is True)
- File: Complete debug logs with stack traces (always DEBUG level)
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from app.core.config import settings


def setup_cli_logging(command_name: str, verbose: bool = False) -> logging.Logger:
    """
    Set up logging for CLI commands.

    Dual logging strategy:
      - Console: Clean, user-friendly output (INFO level)
      - File: Complete debug logs with stack traces (DEBUG level)

    When verbose=True:
      - Console: Still clean INFO messages (no stack traces)
      - File: Full DEBUG traces, stack traces, internal details

    This keeps console output clean while preserving full debugging
    information in persistent log files.

    Args:
        command_name: Command name (e.g., "import", "auth")
        verbose: Enable verbose file logging (console stays clean)

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(f"journiv.cli.{command_name}")
    logger.setLevel(logging.DEBUG)  # Always DEBUG to capture everything
    logger.handlers.clear()  # Remove existing handlers

    # Console handler (rich)
    console_handler = RichHandler(
        console=Console(stderr=True),
        show_time=False,
        show_path=False,
        rich_tracebacks=verbose,  # Enable rich tracebacks if verbose
    )
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler - Always DEBUG with full details
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"cli_{command_name}_{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)  # Always full DEBUG in file
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Log initialization message to file only (DEBUG level)
    logger.debug(f"CLI logging initialized: {log_file}")
    logger.debug(f"Verbose mode: {verbose}")

    return logger
