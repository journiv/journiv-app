"""
Graceful signal handling for long-running CLI operations.

Handles SIGINT/SIGTERM to allow cleanup before exit.
"""
import signal
import sys
from typing import Callable, Optional

from rich.console import Console

console = Console()


class GracefulInterruptHandler:
    """
    Handle SIGINT/SIGTERM gracefully during long-running operations.

    Usage:
        with GracefulInterruptHandler(cleanup_func=cleanup) as handler:
            for item in large_dataset:
                if handler.interrupted:
                    console.print("[yellow]Interrupted by user, cleaning up...[/yellow]")
                    break
                process(item)
    """

    def __init__(self, cleanup_func: Optional[Callable] = None):
        """
        Initialize signal handler.

        Args:
            cleanup_func: Optional function to call on interrupt
        """
        self.interrupted = False
        self.cleanup_func = cleanup_func
        self.original_sigint = None
        self.original_sigterm = None

    def __enter__(self):
        """Set up signal handlers."""
        self.interrupted = False
        self.original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self.original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original handlers and run cleanup."""
        # Restore original handlers
        signal.signal(signal.SIGINT, self.original_sigint)
        signal.signal(signal.SIGTERM, self.original_sigterm)

        # Run cleanup if interrupted
        if self.interrupted and self.cleanup_func:
            try:
                self.cleanup_func()
            except Exception as e:
                console.print(f"[red]Cleanup failed: {e}[/red]")

    def _signal_handler(self, signum, frame):
        """Handle interrupt signal."""
        if not self.interrupted:
            self.interrupted = True
            sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
            console.print(f"\n[yellow]Received {sig_name}, shutting down gracefully...[/yellow]")
            console.print("[yellow]Press Ctrl+C again to force quit (may leave partial data)[/yellow]")
        else:
            # Second interrupt - force quit
            console.print("[red]Force quit! Data may be incomplete.[/red]")
            sys.exit(1)
