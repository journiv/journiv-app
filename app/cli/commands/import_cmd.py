"""
Import command for CLI.

Handles large file imports bypassing web upload limits.
"""
import typer
import tempfile
import shutil
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.logging_config import log_info, log_warning, log_error
from app.models.enums import ImportSourceType
from app.models.import_job import ImportJob
from app.services.import_service import ImportService
from app.services.user_service import UserService
from app.utils.import_export.zip_handler import ZipHandler
from app.cli.logging import setup_cli_logging
from app.cli.commands.preflight import run_preflight_checks
from app.cli.commands.signal_handler import GracefulInterruptHandler
from app.cli.commands.utils import display_import_summary, display_zip_info, confirm_action

app = typer.Typer(help="Import data from files")
console = Console()


@app.command("import-data")
def import_data(
    file_path: Path = typer.Argument(..., help="Path to import ZIP file", exists=True),
    user_email: str = typer.Option(..., "--user-email", "-u", help="User email to import for"),
    source_type: str = typer.Option(
        "journiv",
        "--source-type", "-s",
        help="Import source type (journiv, dayone)",
        case_sensitive=False,
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without importing"),
    skip_preflight: bool = typer.Option(False, "--skip-preflight", help="Skip pre-flight checks"),
    force: bool = typer.Option(False, "--force", help="Force import on critical failures"),
    skip_media_validation: bool = typer.Option(
        False,
        "--skip-media-validation",
        help="Skip libmagic media type validation (much faster for large imports)"
    ),
    max_entry_size_mb: int = typer.Option(
        50000,
        "--max-entry-size-mb",
        help="Maximum size for individual entry/media file in MB (default 50GB for CLI)"
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
):
    """
    Import large data files directly from server filesystem.

    Supports:
      - journiv: Journiv export format (default)
      - dayone: Day One journal exports

    Examples:
      # Journiv import
      python -m app.cli import import-data /data/export.zip --user-email admin@example.com

      # Day One import
      python -m app.cli import import-data /data/dayone.zip -s dayone -u user@example.com

      # Dry run
      python -m app.cli import import-data /data/export.zip -u admin@example.com --dry-run
    """
    # Setup logging
    logger = setup_cli_logging("import", verbose=verbose)
    logger.info(f"Starting import: {file_path} ({source_type})")

    # Validate source type fast
    try:
        source_enum = ImportSourceType(source_type.lower())
    except ValueError:
        console.print(f"\n[red]Invalid source type: {source_type}[/red]")
        console.print("Valid types: journiv, dayone")
        raise typer.Exit(code=2) from None

    try:
        # Pre-flight checks
        if not skip_preflight:
            console.print("\n[bold cyan]Running Pre-Flight Checks...[/bold cyan]")
            check_results = run_preflight_checks(file_path)

            if not check_results["all_passed"]:
                if check_results["has_critical_failures"] and not force:
                    console.print("\n[red]Critical pre-flight checks failed.[/red]")
                    console.print("[yellow]Use --force to proceed (may cause issues)[/yellow]")
                    raise typer.Exit(code=2)
                elif not force:
                    console.print("\n[yellow]Some checks failed, but not critical. Proceeding...[/yellow]")
                else:
                    console.print("\n[yellow]Checks failed, but --force specified. Proceeding...[/yellow]")

        # Validate ZIP structure
        with console.status(
            "[bold cyan]Verifying file integrity (this may take a few minutes for large files)...[/bold cyan]",
            spinner="dots"
        ):
            validation = ZipHandler.validate_zip_structure(file_path, source_enum.value)

        if not validation["valid"]:
            console.print("\n[red]Invalid ZIP:[/red]")
            for error in validation["errors"]:
                console.print(f"  • {error}")
            raise typer.Exit(code=2)

        console.print("[green]✓ ZIP validation passed[/green]")

        # Find user
        with Session(engine) as db:
            user_service = UserService(db)
            user = user_service.get_user_by_email(user_email)
            if not user:
                console.print(f"\n[red]User not found: {user_email}[/red]")
                raise typer.Exit(code=3)

            user_id = user.id
            user_email_val = user.email
            logger.info(f"Found user: {user_email_val} (ID: {user_id})")

        # Dry run exit
        if dry_run:
            console.print("\n[green]✓ Validation passed (dry run)[/green]")
            display_zip_info(validation)
            raise typer.Exit(code=0)

        # Confirm large import
        file_size_gb = file_path.stat().st_size / (1024**3)
        if file_size_gb > 1.0:
            if not confirm_action(f"\nImport {file_size_gb:.2f}GB file? This may take a while.", default=True):
                console.print("[yellow]Import cancelled[/yellow]")
                raise typer.Exit(code=0)


        # Create import job
        with Session(engine) as db:
            import_service = ImportService(db)
            job = import_service.create_import_job(
                user_id=user_id,
                source_type=source_enum,
                file_path=str(file_path),
            )
            db.commit()
            logger.info(f"Created import job: {job.id}")

        # Setup signal handling
        def cleanup():
            logger.warning("Import interrupted, marking job as failed")
            with Session(engine) as db:
                job_db = db.get(ImportJob, job.id)
                if job_db:
                    job_db.mark_failed("Interrupted by user")
                    db.commit()

        with GracefulInterruptHandler(cleanup_func=cleanup) as sig_handler:
            # Extract ZIP with progress
            console.print("\n[bold cyan]Extracting ZIP file...[/bold cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                extract_task = progress.add_task(
                    "Extracting...",
                    total=validation["file_count"]
                )

                def on_extract_progress(current, total):
                    if sig_handler.interrupted:
                        raise KeyboardInterrupt("User interrupted")
                    progress.update(extract_task, completed=current)

                # Use streaming extraction with zero-copy strategy for media
                media_dest = Path(settings.media_root) / str(user_id) / "import_tmp"
                media_dest.mkdir(parents=True, exist_ok=True)

                try:
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp_path = Path(temp_dir)
                        result = ZipHandler.stream_extract(
                            zip_path=file_path,
                            extract_to=temp_path,
                            media_dest=media_dest,
                            max_size_mb=max_entry_size_mb,
                            validate_media=not skip_media_validation,
                            progress_callback=on_extract_progress,
                            source_type=source_enum.value,
                        )

                        data_file = result["data_file"]
                        media_dir = result["media_dir"]

                        # Import data with progress
                        console.print("\n[bold cyan]Importing data...[/bold cyan]")

                        with Session(engine) as db:
                            import_service = ImportService(db)

                            # Count entries for progress
                            if source_enum == ImportSourceType.JOURNIV:
                                import json
                                with open(data_file, 'r') as f:
                                    data = json.load(f)
                                total_entries = sum(len(j.get("entries", [])) for j in data.get("journals", []))
                            else:
                                total_entries = None

                            with Progress(
                                SpinnerColumn(),
                                TextColumn("[progress.description]{task.description}"),
                                BarColumn(),
                                TaskProgressColumn(),
                                console=console,
                            ) as progress:
                                import_task = progress.add_task(
                                    "Importing entries...",
                                    total=total_entries
                                )

                                def on_import_progress(current, total):
                                    if sig_handler.interrupted:
                                        raise KeyboardInterrupt("User interrupted")
                                    progress.update(import_task, completed=current, total=total)

                                # Call appropriate import method
                                if source_enum == ImportSourceType.JOURNIV:
                                    summary = import_service.import_journiv_data(
                                        user_id=user_id,
                                        data=data,
                                        media_dir=media_dir,
                                        total_entries=total_entries,
                                        progress_callback=on_import_progress,
                                    )
                                elif source_enum == ImportSourceType.DAYONE:
                                    summary = import_service.import_dayone_data(
                                        user_id=user_id,
                                        file_path=file_path,
                                        total_entries=total_entries,
                                        progress_callback=on_import_progress,
                                        extraction_dir=temp_path,
                                        media_dir=media_dir,
                                    )
                                else:
                                    console.print(f"\n[red]Unsupported source type: {source_enum}[/red]")
                                    raise typer.Exit(code=2)

                                # Merge extraction warnings into summary
                                if "warnings" in result:
                                    summary.warnings.extend(result["warnings"])
                                if "warning_categories" in result:
                                    for cat, count in result["warning_categories"].items():
                                        summary.warning_categories[cat] = summary.warning_categories.get(cat, 0) + count

                                # Mark job complete
                                job_db = db.get(ImportJob, job.id)
                                if job_db:
                                    job_db.mark_completed(result_data=summary.model_dump())
                                    db.commit()
                finally:
                    # Cleanup media_dest to avoid leaving orphaned files
                    if media_dest.exists():
                        shutil.rmtree(media_dest)

        # Display summary
        console.print("\n[green bold]✓ Import completed successfully[/green bold]")
        display_import_summary(summary)
        logger.info(f"Import completed: {summary.entries_created} entries")

    except KeyboardInterrupt:
        logger.warning("Import interrupted by user")
        console.print("\n[yellow]Import interrupted[/yellow]")
        raise typer.Exit(code=130) from None
    except typer.Exit:
        raise
    except Exception as e:
        logger.error(f"Import failed: {e}", exc_info=True)
        console.print(f"\n[red]Import failed: {e}[/red]")
        console.print("[dim]See log file for details[/dim]")
        raise typer.Exit(code=4) from None
