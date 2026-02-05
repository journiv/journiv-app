"""
Pre-flight checks for import operations.

Validates system state before large imports to prevent failures.
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, Tuple

from rich.console import Console
from rich.table import Table
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine

console = Console()


def check_disk_space(zip_path: Path, required_multiplier: float = 2.5) -> Tuple[bool, str]:
    """
    Check if sufficient disk space exists.

    Rule: Need at least 2.5x ZIP size for:
      - Extracted files (1x)
      - Database growth (0.8x)
      - Media processing (0.5x)
      - Buffer (0.2x)

    Args:
        zip_path: Path to import ZIP file
        required_multiplier: Space multiplier (default: 2.5)

    Returns:
        Tuple of (passed, message)
    """
    if not zip_path.exists():
        return False, f"File not found: {zip_path}"

    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            uncompressed_size = sum(info.file_size for info in zipf.infolist())
    except Exception as e:
        return False, f"Could not read ZIP file: {e}"

    required_space = uncompressed_size * required_multiplier

    try:
        stat = shutil.disk_usage(settings.media_root)
    except FileNotFoundError:
        # Fallback to parent directory if media_root doesn't exist yet
        parent_dir = os.path.dirname(os.path.abspath(settings.media_root))
        stat = shutil.disk_usage(parent_dir)

    available = stat.free

    if available < required_space:
        return False, (
            f"Insufficient disk space: need {required_space / (1024**3):.2f}GB, "
            f"have {available / (1024**3):.2f}GB available"
        )

    return True, f"Disk space OK: {available / (1024**3):.2f}GB available"


def check_write_permissions() -> Tuple[bool, str]:
    """
    Check write permissions for media and logs directories.

    Returns:
        Tuple of (passed, message)
    """
    test_dirs = [
        Path(settings.media_root),
        Path(settings.log_dir),
    ]

    for dir_path in test_dirs:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            test_file = dir_path / f".write_test_{os.getpid()}"
            try:
                test_file.write_text("test")
            finally:
                if test_file.exists():
                    try:
                        test_file.unlink()
                    except Exception:
                        pass
        except (PermissionError, OSError) as e:
            return False, f"No write access to {dir_path}: {e}"

    return True, "Write permissions OK"


def check_pending_migrations() -> Tuple[bool, str]:
    """
    Check if there are pending Alembic migrations.

    Returns:
        Tuple of (passed, message)
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        # Try to find alembic.ini
        alembic_ini = Path("alembic.ini")
        if not alembic_ini.exists():
            # Try relative to backend directory
            backend_dir = Path(__file__).parent.parent.parent.parent
            alembic_ini = backend_dir / "alembic.ini"

        if not alembic_ini.exists():
            return False, "Alembic config (alembic.ini) not found"

        config = Config(str(alembic_ini))
        script = ScriptDirectory.from_config(config)

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            head_rev = script.get_current_head()

            if current_rev != head_rev:
                return False, (
                    f"Pending migrations: current={current_rev}, head={head_rev}. "
                    f"Run 'alembic upgrade head' first."
                )

            return True, "Database migrations up to date"
    except Exception as e:
        return False, f"Failed to check migrations: {e}"


def check_database_connection() -> Tuple[bool, str]:
    """
    Verify database connection.

    Returns:
        Tuple of (passed, message)
    """
    try:
        with Session(engine) as db:
            # Simple query to test connection
            from sqlmodel import select
            db.exec(select(1)).first()
        return True, "Database connection OK"
    except Exception as e:
        return False, f"Database connection failed: {e}"


def run_preflight_checks(zip_path: Path) -> Dict[str, Any]:
    """
    Run all pre-flight checks and display results.

    Args:
        zip_path: Path to import ZIP file

    Returns:
        Dictionary with:
        - all_passed: True if all checks pass
        - has_critical_failures: True if critical checks failed (requires --force)
        - results: List of check results
    """
    # Define checks with criticality level
    checks = [
        ("Database Connection", check_database_connection, True),  # Critical
        ("Disk Space", lambda: check_disk_space(zip_path), True),  # Critical
        ("Write Permissions", check_write_permissions, True),  # Critical
        ("Pending Migrations", check_pending_migrations, True),   # Critical
    ]

    table = Table(title="Pre-Flight Checks")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")
    table.add_column("Criticality", style="dim")

    all_passed = True
    has_critical_failures = False
    results = []

    for check_name, check_func, is_critical in checks:
        try:
            passed, message = check_func()
            level = "[bold red]HIGH[/bold red]" if is_critical else "[yellow]MEDIUM[/yellow]"

            results.append({
                "name": check_name,
                "passed": passed,
                "message": message,
                "is_critical": is_critical
            })

            if passed:
                status = "[green]✓ PASS[/green]"
            elif is_critical:
                status = "[red]✗ FAIL[/red]"
                has_critical_failures = True
            else:
                status = "[yellow]⚠ WARN[/yellow]"

            table.add_row(check_name, status, message, level)

            if not passed:
                all_passed = False
        except Exception as e:
            level = "[bold red]HIGH[/bold red]" if is_critical else "[yellow]MEDIUM[/yellow]"
            results.append({
                "name": check_name,
                "passed": False,
                "message": str(e),
                "is_critical": is_critical,
                "error": True
            })
            table.add_row(check_name, "[red]✗ ERROR[/red]", str(e), level)
            all_passed = False
            if is_critical:
                has_critical_failures = True

    console.print(table)

    return {
        "all_passed": all_passed,
        "has_critical_failures": has_critical_failures,
        "results": results,
    }
