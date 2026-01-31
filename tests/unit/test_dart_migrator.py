import json
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def migrator_path():
    """Path to compiled Dart binary."""
    base = Path(__file__).resolve().parents[2] / "bin"
    for name in ("migrator", "migrator-test"):
        candidate = base / name
        if candidate.exists():
            return candidate
    pytest.skip("Dart migrator binary not found (build /app/bin/migrator first)")


def test_simple_markdown(migrator_path):
    """Test basic Markdown conversion."""
    markdown = "**Bold** and *italic* text"
    result = subprocess.run(
        [str(migrator_path)],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    delta = json.loads(result.stdout)
    assert "ops" in delta
    assert delta["ops"][0]["insert"] == "Bold"
    assert delta["ops"][0]["attributes"]["bold"] is True


def test_highlight_syntax(migrator_path):
    """Test custom ==highlight== syntax."""
    markdown = "Text with ==highlighted== portion"
    result = subprocess.run(
        [str(migrator_path)],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    delta = json.loads(result.stdout)
    ops = delta["ops"]
    highlighted = [op for op in ops if "highlight" in op.get("attributes", {})]
    assert len(highlighted) == 1
    assert highlighted[0]["insert"] == "highlighted"


def test_media_shortcode(migrator_path):
    """Test media shortcode handling (stripped for migration)."""
    markdown = "Text with image: ![[media:550e8400-e29b-41d4-a716-446655440000]]"
    result = subprocess.run(
        [str(migrator_path)],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    delta = json.loads(result.stdout)
    assert "ops" in delta


def test_invalid_markdown(migrator_path):
    """Test error handling for malformed input."""
    markdown = "\uFFFE\uFFFFinvalid unicode"
    result = subprocess.run(
        [str(migrator_path)],
        input=markdown,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0


def test_stdin_input(migrator_path):
    """Test stdin-based input (only supported input method)."""
    markdown = "**Bold**"
    result = subprocess.run(
        [str(migrator_path)],
        input=markdown,
        capture_output=True,
        text=True,
        check=True,
    )
    delta = json.loads(result.stdout)
    assert "ops" in delta


def test_rejects_command_line_arguments(migrator_path):
    """Test that command-line arguments are rejected."""
    result = subprocess.run(
        [str(migrator_path), "**Bold**"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Command-line arguments are not supported" in result.stderr


def test_empty_stdin(migrator_path):
    """Test handling of empty stdin input."""
    result = subprocess.run(
        [str(migrator_path)],
        input="",
        capture_output=True,
        text=True,
        check=True,
    )
    delta = json.loads(result.stdout)
    # Empty content should produce valid Quill Delta with newline
    assert delta == {"ops": [{"insert": "\n"}]}
