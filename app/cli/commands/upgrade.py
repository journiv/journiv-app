"""
Upgrade commands for Journiv data transformations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table
from sqlmodel import Session

from app import __version__ as app_version
from app.cli.commands.utils import confirm_action
from app.cli.logging import setup_cli_logging
from app.core.database import engine

app = typer.Typer(help="Upgrade commands", invoke_without_command=True)
console = Console()

MIN_SUPPORTED_REVISION = "c9d2e1f0a1b2"
UPGRADE_STEPS: list[tuple[str, str]] = []


def _resolve_alembic_ini() -> Path:
    alembic_ini = Path("alembic.ini")
    if alembic_ini.exists():
        return alembic_ini
    backend_dir = Path(__file__).parent.parent.parent.parent
    return backend_dir / "alembic.ini"


def _check_version_guard() -> tuple[bool, str]:
    alembic_ini = _resolve_alembic_ini()
    if not alembic_ini.exists():
        return False, "Alembic config (alembic.ini) not found"

    config = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(config)

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()
        head_rev = script.get_current_head()

    if current_rev is None:
        return False, "Database revision not found (alembic_version missing)"

    if current_rev != head_rev:
        return False, (
            f"Pending migrations: current={current_rev}, head={head_rev}. "
            f"Run 'alembic upgrade head' first."
        )

    if current_rev == MIN_SUPPORTED_REVISION:
        return True, "Version guard passed"

    for rev in script.iterate_revisions(current_rev, None):
        if rev.revision == MIN_SUPPORTED_REVISION:
            return True, "Version guard passed"

    return False, (
        f"Upgrade not supported from database revision {current_rev}. "
        f"Minimum supported revision is {MIN_SUPPORTED_REVISION}."
    )


@app.callback()
def run_upgrade(
    batch_size: Annotated[
        int, typer.Option("--batch-size", "-b", help="Moments processed per batch")
    ] = 200,
    assume_yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Run without confirmation prompts")
    ] = False,
):
    if batch_size <= 0:
        raise typer.BadParameter("Batch size must be a positive integer.")

    logger = setup_cli_logging("upgrade", verbose=False)
    logger.info(f"Starting upgrade command (app version {app_version})")

    ok, message = _check_version_guard()
    if not ok:
        console.print(f"[red]{message}[/red]")
        raise typer.Exit(code=2)

    header = Table(title="Upgrade Summary")
    header.add_column("Metric", style="cyan")
    header.add_column("Value", style="white")
    header.add_row("App version", app_version)
    header.add_row("Batch size", str(batch_size))
    header.add_row("Minimum supported revision", MIN_SUPPORTED_REVISION)
    header.add_row("Steps configured", str(len(UPGRADE_STEPS)))
    console.print(header)

    if not UPGRADE_STEPS:
        logger.info("No application-level upgrade steps configured. Exiting.")
        console.print("[green]No application-level upgrade steps required.[/green]")
        raise typer.Exit(code=0)

    if not assume_yes:
        if not confirm_action(
            "\n⚠ This will modify your database. Ensure you have a backup. Continue?",
            default=False,
        ):
            console.print("[yellow]Upgrade cancelled[/yellow]")
            raise typer.Exit(code=0)

    with Session(engine) as session:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Running upgrades...", total=len(UPGRADE_STEPS))
            totals: dict[str, int] = {}

            for step_name, step_fn_name in UPGRADE_STEPS:
                logger.info(f"Running upgrade step: {step_name}")
                step_fn = globals().get(step_fn_name)
                if not callable(step_fn):
                    raise RuntimeError(f"Upgrade step not found: {step_fn_name}")
                totals[step_name] = step_fn(session, batch_size, logger)
                progress.advance(task)

    summary = Table(title="Upgrade Results")
    summary.add_column("Step", style="cyan")
    summary.add_column("Updated", style="white")
    for name, _ in UPGRADE_STEPS:
        summary.add_row(name, str(totals.get(name, 0)))
    console.print(summary)
