"""
Upgrade commands for Journiv data transformations.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeRemainingColumn
from rich.table import Table
from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from app import __version__ as app_version
from app.cli.commands.utils import confirm_action
from app.cli.logging import setup_cli_logging
from app.core.database import engine
from app.models.entry import Entry
from app.utils.quill_delta import (
    extract_plain_text,
    replace_media_ids,
    wrap_dayone_text,
)

app = typer.Typer(help="Upgrade commands")
console = Console()

MIN_SUPPORTED_REVISION = "b7a1c2d3e4f5"
UPGRADE_STEPS = [
    ("dayone_inline_media", "_upgrade_dayone_inline_media"),
]

_DAYONE_MD5_RE = re.compile(r"^[a-fA-F0-9]{32}$")


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


def _extract_md5_candidate(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    stem = Path(value).stem
    if _DAYONE_MD5_RE.match(stem):
        return stem
    match = re.search(r"([a-fA-F0-9]{32})", value)
    return match.group(1) if match else None


def _build_dayone_placeholder_map(entry: Entry) -> dict[str, str]:
    placeholder_map: dict[str, str] = {}
    md5_to_media_id: dict[str, str] = {}

    for media in entry.media or []:
        if media.external_asset_id:
            placeholder_map[media.external_asset_id] = str(media.id)
        if isinstance(media.external_metadata, dict):
            identifier = media.external_metadata.get("identifier")
            md5_hash = media.external_metadata.get("md5")
            if identifier:
                placeholder_map[identifier] = str(media.id)
            if md5_hash:
                placeholder_map[md5_hash] = str(media.id)

        md5 = _extract_md5_candidate(media.original_filename) or _extract_md5_candidate(
            media.file_path
        )
        if md5:
            md5_to_media_id[md5] = str(media.id)

    if md5_to_media_id:
        placeholder_map.update(md5_to_media_id)

    import_metadata = entry.import_metadata or {}
    raw_dayone = (
        import_metadata.get("raw_dayone") if isinstance(import_metadata, dict) else None
    )
    if not isinstance(raw_dayone, dict):
        return placeholder_map

    media_items = (raw_dayone.get("photos") or []) + (raw_dayone.get("videos") or [])
    for item in media_items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("identifier")
        md5_hash = item.get("md5")
        media_id = md5_to_media_id.get(md5_hash) if md5_hash else None
        if media_id:
            placeholder_map[md5_hash] = media_id
            if identifier:
                placeholder_map[identifier] = media_id

    return placeholder_map


def _upgrade_dayone_inline_media(session: Session, batch_size: int, logger) -> int:
    migrated = 0
    last_id = None

    while True:
        query = (
            select(Entry)
            .where(col(Entry.content_plain_text).contains("DAYONE_"))
            .order_by(col(Entry.id))
            .limit(batch_size)
            .options(selectinload(Entry.media))  # type: ignore[arg-type]
        )
        if last_id is not None:
            query = query.where(col(Entry.id) > last_id)

        entries = session.exec(query).all()
        if not entries:
            break

        for entry in entries:
            import_metadata = entry.import_metadata or {}
            if (
                not isinstance(import_metadata, dict)
                or import_metadata.get("source") != "dayone"
            ):
                last_id = entry.id
                continue
            if not entry.content_delta:
                last_id = entry.id
                continue

            text = extract_plain_text(entry.content_delta)
            if "DAYONE_" not in text:
                last_id = entry.id
                continue

            placeholder_map = _build_dayone_placeholder_map(entry)
            if not placeholder_map:
                last_id = entry.id
                continue

            new_delta = wrap_dayone_text(text)
            new_delta = replace_media_ids(new_delta, placeholder_map)
            entry.content_delta = new_delta
            session.add(entry)
            migrated += 1
            last_id = entry.id

        session.commit()
        logger.info(f"Upgraded batch ending at {last_id}, migrated={migrated}")

    return migrated


@app.command("upgrade")
def run_upgrade(
    batch_size: Annotated[
        int, typer.Option("--batch-size", "-b", help="Entries processed per batch")
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
    header.add_row("Steps", ", ".join([name for name, _ in UPGRADE_STEPS]))
    console.print(header)

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
