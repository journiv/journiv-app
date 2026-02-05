"""
Authentication management commands.

Handles user password recovery and management.
"""
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt
from sqlmodel import Session

from app.core.database import engine
from app.core.logging_config import log_info, log_warning
from app.core.security import get_password_hash
from app.services.user_service import UserService

app = typer.Typer(help="User authentication management")
console = Console()


@app.command("change-password")
def change_password(
    email: str = typer.Option(..., "--email", "-e", help="User email"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="New password (prompt if not provided)"),
):
    """
    Change user password (admin recovery tool).

    Use this command when an admin is locked out or needs to reset a user's password.

    Examples:
      # Interactive password prompt (recommended)
      python -m app.cli auth change-password --email admin@example.com

      # Direct password (less secure - visible in shell history)
      python -m app.cli auth change-password --email user@example.com --password newsecurepass123

    Docker:
      docker compose exec app python -m app.cli auth change-password -e admin@example.com
    """
    try:
        # Warn if password provided via CLI (shell history risk)
        if password:
            console.print("[yellow]Warning: Password provided via command line is visible in shell history[/yellow]")
            console.print("[yellow]Consider using interactive prompt instead (omit --password flag)[/yellow]\n")

        # Prompt for password if not provided
        if not password:
            password = Prompt.ask("Enter new password", password=True)
            confirm = Prompt.ask("Confirm new password", password=True)

            if password != confirm:
                console.print("[red]Passwords do not match[/red]")
                raise typer.Exit(code=1)

        # Validate password strength (basic)
        if len(password) < 8:
            console.print("[red]Password must be at least 8 characters[/red]")
            raise typer.Exit(code=1)

        # Update password
        with Session(engine) as db:
            user_service = UserService(db)
            user = user_service.get_user_by_email(email)

            if not user:
                console.print(f"[red]User not found: {email}[/red]")
                raise typer.Exit(code=3)

            # Hash password
            hashed = get_password_hash(password)

            # Update user
            user.password = hashed
            db.commit()

            console.print(f"\n[green]✓ Password changed successfully for {email}[/green]")
            log_info(f"Password changed for user: {email}", user_id=str(user.id))

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        log_warning(f"Password change failed: {e}", email=email)
        raise typer.Exit(code=4) from None
