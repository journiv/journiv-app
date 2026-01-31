"""
Migration commands for Journiv data.
"""
from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from sqlalchemy import text
from sqlmodel import Session, select

from app.cli.commands.utils import confirm_action
from app.cli.logging import setup_cli_logging
from app.core.database import engine
from app.models.entry import Entry, EntryMedia
from app.models.enums import MediaType
from app.schemas.entry import QuillDelta
from app.utils.quill_delta import extract_plain_text

app = typer.Typer(help="Data migration commands")
console = Console()


def _resolve_migrator_path() -> Path:
    docker_bin = Path("/usr/local/bin/migrator")
    if docker_bin.exists():
        return docker_bin

    docker_path = Path("/app/bin/migrator")
    if docker_path.exists():
        return docker_path

    repo_path = Path(__file__).resolve().parents[3] / "bin" / "migrator"
    if repo_path.exists():
        return repo_path

    dev_path = Path(__file__).resolve().parents[3] / "bin" / "migrator-test"
    if dev_path.exists():
        return dev_path

    return docker_bin


def _log_error(
    error_log: Path,
    entry_id: str,
    error: str,
    *,
    content_preview: Optional[str] = None,
    delta_output: Optional[str] = None,
    stderr: Optional[str] = None,
) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with error_log.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} | ENTRY_ID: {entry_id} | ERROR: {error}\n")
        if content_preview:
            handle.write(f"  Content preview: {content_preview}\n")
        if delta_output:
            handle.write(f"  Delta output: {delta_output}\n")
        if stderr:
            handle.write(f"  Subprocess stderr: {stderr}\n")
        handle.write("---\n")


def _expand_media_shortcodes(markdown: str, media_items: list[EntryMedia]) -> str:
    if not markdown:
        return markdown
    if "![[media:" not in markdown:
        return markdown

    media_map = {str(item.id): item.media_type for item in media_items}

    def replace(match):
        media_id = match.group(1)
        media_type = media_map.get(media_id, MediaType.IMAGE)
        if media_type == MediaType.VIDEO:
            return f":::video {media_id}:::"
        if media_type == MediaType.AUDIO:
            return f":::audio {media_id}:::"
        return f"![]({media_id})"

    return re.sub(r'!\[\[media:([a-fA-F0-9-]{36})\]\]', replace, markdown)


@app.command("content")
def migrate_content(
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Entries processed per batch"),
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Maximum entries to migrate (for testing)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview migration without database changes"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt"),
    cleanup: bool = typer.Option(False, "--cleanup", help="Clear legacy content after successful migration"),
    error_log: Path = typer.Option("migration_errors.log", "--error-log", "-e", help="Path for error log file"),
):
    """
    Migrate Markdown content to Quill Delta JSON format.

    This command:
    - Queries entries where content_delta IS NULL
    - Converts legacy 'content' (Markdown) to Delta using Dart binary
    - Validates output with Pydantic schema before saving
    - Processes in configurable batches to prevent memory spikes
    - Skips failed entries and logs errors for manual review
    """
    if batch_size <= 0:
        raise typer.BadParameter("Batch size must be a positive integer.")

    logger = setup_cli_logging("migrate", verbose=verbose)
    logger.info("Starting content migration command")
    logger.info(f"Options: batch_size={batch_size}, limit={limit}, dry_run={dry_run}, cleanup={cleanup}")

    migrator_path = _resolve_migrator_path()
    logger.info(f"Resolved migrator path: {migrator_path}")

    if not migrator_path.exists():
        logger.error(f"Migrator binary not found at {migrator_path}")
        console.print(f"[red]Migrator binary not found at {migrator_path}[/red]")
        raise typer.Exit(code=2)

    with Session(engine) as session:
        total_query = session.exec(
            text(
                "SELECT COUNT(*) FROM entry "
                "WHERE content_delta IS NULL AND content IS NOT NULL AND content != ''"
            )
        ).one()
        total_entries = int(total_query[0])
        logger.info(f"Found {total_entries} entries to migrate")

        if total_entries == 0:
            logger.info("No entries to migrate")
            if cleanup:
                cleanup_count = session.exec(
                    text("SELECT COUNT(*) FROM entry WHERE content_delta IS NOT NULL AND content IS NOT NULL")
                ).one()[0]
                logger.info(f"Found {cleanup_count} entries eligible for cleanup")
                cleanup_table = Table(title="Cleanup Summary")
                cleanup_table.add_column("Metric", style="cyan")
                cleanup_table.add_column("Value", style="white")
                cleanup_table.add_row("Entries eligible for cleanup", str(cleanup_count))
                console.print(cleanup_table)

                if cleanup_count == 0:
                    logger.info("No legacy content to clean")
                    console.print("[green]No legacy content to clean.[/green]")
                    raise typer.Exit(code=0)

                if dry_run:
                    logger.info("Cleanup dry run complete")
                    console.print("[green]✓ Dry run complete. No changes applied.[/green]")
                    raise typer.Exit(code=0)

                if not force:
                    if not confirm_action(
                        "\n⚠ This will clear legacy content for the entries above. Continue?",
                        default=False,
                    ):
                        logger.info("Cleanup cancelled by user")
                        console.print("[yellow]Cleanup cancelled[/yellow]")
                        raise typer.Exit(code=0)

                console.print("[yellow]No entries to migrate. Running cleanup...[/yellow]")
                logger.info(f"Starting cleanup of {cleanup_count} entries")
                session.exec(
                    text("UPDATE entry SET content = NULL WHERE content_delta IS NOT NULL")
                )
                session.commit()
                logger.info(f"Cleanup complete for {cleanup_count} entries")
                console.print("[green]✓ Cleanup complete[/green]")
                raise typer.Exit(code=0)
            logger.info("All entries already migrated")
            console.print("[green]All entries already migrated.[/green]")
            raise typer.Exit(code=0)

        total_to_migrate = min(total_entries, limit) if limit else total_entries
        logger.info(f"Total entries to migrate: {total_to_migrate}")

        header = Table(title="Markdown → Delta Migration")
        header.add_column("Metric", style="cyan")
        header.add_column("Value", style="white")
        header.add_row("Total entries to migrate", str(total_entries))
        header.add_row("Batch size", str(batch_size))
        header.add_row("Mode", "DRY RUN" if dry_run else "LIVE")
        if limit:
            header.add_row("Limit", str(limit))
        console.print(header)

        if verbose:
            preview_rows = session.exec(
                text(
                    "SELECT id, content FROM entry "
                    "WHERE content_delta IS NULL AND content IS NOT NULL AND content != '' "
                    "ORDER BY entry_datetime_utc DESC LIMIT 5"
                )
            ).all()
            if preview_rows:
                logger.info(f"Preview of {len(preview_rows)} entries to migrate")
                console.print("\n[bold cyan]Preview (first entries):[/bold cyan]")
                for row in preview_rows:
                    preview = (row.content or "").replace("\n", " ").strip()
                    if len(preview) > 140:
                        preview = f"{preview[:140]}..."
                    console.print(f"  • {row.id} | {preview}")

        if not force:
            if not confirm_action("\n⚠ This will modify your database. Ensure you have a backup. Continue?", default=False):
                logger.info("Migration cancelled by user")
                console.print("[yellow]Migration cancelled[/yellow]")
                raise typer.Exit(code=0)

        if dry_run:
            logger.info(f"Dry run complete - would process {total_to_migrate} entries")
            console.print(f"\n[green]✓ Dry run complete. {total_to_migrate} entries would be processed.[/green]")
            raise typer.Exit(code=0)

        logger.info(f"Starting migration of {total_to_migrate} entries in batches of {batch_size}")

        migrated = 0
        skipped = 0
        errors = 0
        processed = 0

        started_at = datetime.now()
        last_entry_datetime = None
        last_entry_id = None

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Migrating entries...", total=total_to_migrate)

            while processed < total_to_migrate:
                remaining = total_to_migrate - processed
                batch_limit = min(batch_size, remaining)

                if last_entry_datetime is None:
                    query = (
                        "SELECT id, content, entry_datetime_utc FROM entry "
                        "WHERE content_delta IS NULL AND content IS NOT NULL AND content != '' "
                        "ORDER BY entry_datetime_utc DESC, id DESC LIMIT :limit"
                    )
                    params = {"limit": batch_limit}
                else:
                    query = (
                        "SELECT id, content, entry_datetime_utc FROM entry "
                        "WHERE content_delta IS NULL AND content IS NOT NULL AND content != '' "
                        "AND (entry_datetime_utc < :last_dt OR (entry_datetime_utc = :last_dt AND id < :last_id)) "
                        "ORDER BY entry_datetime_utc DESC, id DESC LIMIT :limit"
                    )
                    params = {
                        "limit": batch_limit,
                        "last_dt": last_entry_datetime,
                        "last_id": last_entry_id,
                    }

                rows = session.exec(text(query).bindparams(**params)).all()

                if not rows:
                    break

                entry_ids = [row.id for row in rows]
                media_items = session.exec(
                    select(EntryMedia).where(EntryMedia.entry_id.in_(entry_ids))
                ).all()
                media_by_entry = {}
                for media in media_items:
                    media_by_entry.setdefault(media.entry_id, []).append(media)

                # End the read transaction early to avoid long-running/idle transactions
                session.commit()

                updates = []

                for row in rows:
                    entry_id = str(row.id)
                    content = row.content or ""
                    processed += 1
                    progress.advance(task, 1)

                    if not content.strip():
                        skipped += 1
                        continue

                    entry_uuid = row.id
                    content = _expand_media_shortcodes(
                        content,
                        list(media_by_entry.get(entry_uuid, [])),
                    )

                    try:
                        result = subprocess.run(
                            [str(migrator_path)],
                            input=content,
                            capture_output=True,
                            text=True,
                            timeout=30,
                        )
                    except subprocess.TimeoutExpired:
                        errors += 1
                        logger.error(f"Subprocess timeout (30s) for entry {entry_id}")
                        _log_error(
                            error_log,
                            entry_id,
                            "Subprocess timeout (30s)",
                            content_preview=content[:200].replace("\n", " "),
                        )
                        continue

                    if result.returncode != 0:
                        errors += 1
                        logger.error(f"Migration binary failed (exit {result.returncode}) for entry {entry_id}")
                        _log_error(
                            error_log,
                            entry_id,
                            f"Migration binary failed (exit {result.returncode})",
                            content_preview=content[:200].replace("\n", " "),
                            stderr=result.stderr.strip() or None,
                        )
                        continue

                    try:
                        delta_json = json.loads(result.stdout)
                    except json.JSONDecodeError as exc:
                        errors += 1
                        logger.error(f"Invalid JSON output for entry {entry_id}: {exc}")
                        _log_error(
                            error_log,
                            entry_id,
                            f"Invalid JSON output: {exc}",
                            content_preview=content[:200].replace("\n", " "),
                            delta_output=result.stdout[:500],
                            stderr=result.stderr.strip() or None,
                        )
                        continue

                    try:
                        delta_model = QuillDelta.model_validate(delta_json)
                        delta_payload = delta_model.model_dump()
                    except ValidationError as exc:
                        errors += 1
                        logger.error(f"Pydantic validation failed for entry {entry_id}: {exc}")
                        _log_error(
                            error_log,
                            entry_id,
                            f"Pydantic validation failed: {exc}",
                            content_preview=content[:200].replace("\n", " "),
                            delta_output=json.dumps(delta_json)[:500],
                        )
                        continue

                    plain_text = extract_plain_text(delta_payload)
                    migrated += 1

                    updates.append(
                        {
                            "entry_id": entry_uuid,
                            "delta": delta_payload,
                            "plain_text": plain_text,
                            "word_count": len(plain_text.split()) if plain_text else 0,
                        }
                    )

                if updates:
                    entries = session.exec(
                        select(Entry).where(Entry.id.in_([u["entry_id"] for u in updates]))
                    ).all()
                    entry_map = {entry.id: entry for entry in entries}
                    for update in updates:
                        entry = entry_map.get(update["entry_id"])
                        if not entry:
                            errors += 1
                            logger.error(f"Entry not found during update: {update['entry_id']}")
                            _log_error(
                                error_log,
                                str(update["entry_id"]),
                                "Entry not found during update",
                            )
                            continue
                        entry.content_delta = update["delta"]
                        entry.content_plain_text = update["plain_text"] or None
                        entry.word_count = update["word_count"]
                        session.add(entry)
                    session.commit()
                    logger.info(f"Migrated batch: {len(updates)} entries saved to database")

                last_entry_datetime = rows[-1].entry_datetime_utc
                last_entry_id = rows[-1].id

        duration = datetime.now() - started_at
        duration_seconds = max(duration.total_seconds(), 1)
        speed = migrated / duration_seconds

        summary = Table(title="Migration Summary")
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="green")
        summary.add_row("Total queried", str(total_to_migrate))
        summary.add_row("Migrated successfully", str(migrated))
        summary.add_row("Skipped (empty content)", str(skipped))
        summary.add_row("Failed (errors)", str(errors))
        summary.add_row("Average speed", f"{speed:.2f} entries/sec")
        summary.add_row("Duration", str(duration).split(".")[0])
        summary.add_row("Error log", str(error_log))

        logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped, {errors} errors in {duration_seconds:.2f}s ({speed:.2f} entries/sec)")

        if cleanup:
            cleanup_count = session.exec(
                text("SELECT COUNT(*) FROM entry WHERE content_delta IS NOT NULL AND content IS NOT NULL")
            ).one()[0]
            logger.info(f"Found {cleanup_count} entries eligible for cleanup")
            if cleanup_count > 0:
                cleanup_table = Table(title="Cleanup Summary")
                cleanup_table.add_column("Metric", style="cyan")
                cleanup_table.add_column("Value", style="white")
                cleanup_table.add_row("Entries eligible for cleanup", str(cleanup_count))
                console.print(cleanup_table)

                if not force:
                    if not confirm_action(
                        "\n⚠ This will clear legacy content for the entries above. Continue?",
                        default=False,
                    ):
                        logger.info("Cleanup cancelled by user")
                        console.print("[yellow]Cleanup cancelled[/yellow]")
                        raise typer.Exit(code=0)

            console.print("\n[yellow]Cleaning up legacy content field...[/yellow]")
            logger.info(f"Starting cleanup of {cleanup_count} entries")
            session.exec(
                text("UPDATE entry SET content = NULL WHERE content_delta IS NOT NULL")
            )
            session.commit()
            logger.info(f"Cleanup complete for {cleanup_count} entries")

        console.print("\n[green]✓ Migration complete[/green]")
        console.print(summary)

        if errors:
            logger.warning(f"{errors} entries failed. See {error_log} for details")
            console.print(f"\n[yellow]⚠ {errors} entries failed. Review: {error_log}[/yellow]")
