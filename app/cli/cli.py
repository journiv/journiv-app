"""
Main CLI application using Typer.

Entry point: python -m app.cli
CLI Name: journiv-admin
"""
import typer

from app import __version__ as app_version
from app.cli.commands import auth, import_cmd, migrate, upgrade

app = typer.Typer(
    name="journiv-admin",
    help="Journiv Admin CLI - System Administration Tools for Self-Hosted Journiv",
)

@app.command()
def version():
    """Show CLI version information."""
    typer.echo(f"Journiv CLI version {app_version}")

# Register command groups


app.add_typer(import_cmd.app, name="import")
app.add_typer(auth.app, name="auth")
app.add_typer(migrate.app, name="migrate")
app.add_typer(upgrade.app, name="upgrade")
