"""
Main CLI application using Typer.

Entry point: python -m app.cli
CLI Name: journiv-admin
"""
import typer

from app import __version__ as app_version

app = typer.Typer(
    name="journiv-admin",
    help="Journiv Admin CLI - System Administration Tools for Self-Hosted Journiv",
)

@app.command()
def version():
    """Show CLI version information."""
    typer.echo(f"Journiv CLI version {app_version}")

# Register command groups
from app.cli.commands import import_cmd, auth, migrate
app.add_typer(import_cmd.app, name="import")
app.add_typer(auth.app, name="auth")
app.add_typer(migrate.app, name="migrate")
