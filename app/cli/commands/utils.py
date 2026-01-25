"""
CLI utility functions for display and formatting.
"""
from pathlib import Path
from typing import Any, Dict
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

console = Console()


def display_import_summary(summary: Any):
    """
    Display formatted import summary.

    Args:
        summary: ImportSummary object with import results
    """
    table = Table(title="Import Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")

    table.add_row("Journals Created", str(summary.journals_created))
    table.add_row("Entries Created", str(summary.entries_created))
    table.add_row("Media Files Imported", str(summary.media_files_imported))
    table.add_row("Tags Created", str(summary.tags_created))

    if summary.warnings:
        table.add_row("Total Warnings", str(len(summary.warnings)), style="yellow")

    # Detailed warning categories
    if hasattr(summary, 'warning_categories') and summary.warning_categories:
        for category, count in summary.warning_categories.items():
            table.add_row(f"  • {category}", str(count), style="dim yellow")

    console.print(table)

    if summary.warnings:
        console.print("\n[yellow]Warnings:[/yellow]")
        for warning in summary.warnings[:10]:  # Show first 10
            console.print(f"  • {warning}")

        if len(summary.warnings) > 10:
            console.print(f"  ... and {len(summary.warnings) - 10} more warnings (check logs)")


def display_zip_info(validation: Dict[str, Any]):
    """
    Display ZIP validation information.

    Args:
        validation: Validation result dictionary
    """
    table = Table(title="ZIP File Information")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Valid", "✓ Yes" if validation["valid"] else "✗ No")
    table.add_row("Has Data File", "✓ Yes" if validation["has_data_file"] else "✗ No")
    table.add_row("Has Media", "✓ Yes" if validation["has_media"] else "✗ No")
    table.add_row("File Count", str(validation["file_count"]))
    table.add_row("Total Size", format_file_size(validation["total_size"]))

    if validation.get("errors"):
        table.add_row("Errors", str(len(validation["errors"])), style="red")

    console.print(table)

    if validation.get("errors"):
        console.print("\n[red]Errors:[/red]")
        for error in validation["errors"]:
            console.print(f"  • {error}")


def confirm_action(message: str, default: bool = False) -> bool:
    """
    Prompt for user confirmation.

    Args:
        message: Confirmation message
        default: Default response

    Returns:
        True if user confirmed, False otherwise
    """
    return Confirm.ask(message, default=default)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
