import os
import shutil
import sys
from pathlib import Path

try:
    import PyInstaller.__main__
except ImportError:
    print("Error: PyInstaller is not installed.")
    print("Install it with: pip install pyinstaller")
    sys.exit(1)


def setup_build_environment():
    print("Checking build dependencies...")
    required = ["uvicorn", "fastapi", "sqlalchemy", "pydantic"]
    missing = []

    for module in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(module)

    if missing:
        print(f"Error: Missing modules: {', '.join(missing)}")
        return False

    print("✓ All build dependencies found")
    return True


def get_project_root():
    return Path(__file__).parent.parent.resolve()


def get_hidden_imports():
    return [
        "app", "app.api", "app.api.v1", "app.api.v1.api", "app.api.v1.endpoints",
        "app.core", "app.core.config", "app.core.database", "app.core.exceptions",
        "app.middleware", "app.models", "app.schemas", "app.services",
        "app.tasks", "app.utils", "app.cli", "app.integrations",
        "uvicorn.workers.uvicornworker", "sqlalchemy.dialects.sqlite",
        "sqlalchemy.pool", "alembic", "alembic.config", "alembic.command",
        "pydantic", "pydantic_settings", "fastapi", "starlette", "typing_extensions",
    ]


def get_binaries():
    binaries = []
    try:
        import sqlite3
        sqlite3_path = Path(sqlite3.__file__).parent
        if sqlite3_path.exists():
            binaries.append((str(sqlite3_path), "sqlite3"))
    except ImportError:
        pass
    return binaries


def build_executable():
    project_root = get_project_root()
    build_dir = project_root / "build"
    dist_dir = project_root / "dist"

    print(f"\nProject root: {project_root}")
    print(f"Build output: {dist_dir}")

    datas = [
        (str(project_root / "app" / "static"), "app/static"),
        (str(project_root / "app" / "templates"), "app/templates"),
        (str(project_root / "web"), "web"),
        (str(project_root / "alembic"), "alembic"),
    ]

    print("\nCleaning previous builds...")
    if build_dir.exists():
        shutil.rmtree(build_dir)
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    args = [
        str(project_root / "app" / "main.py"),
        "--onefile",
        "--windowed",
        "--name", "journiv",
        "--distpath", str(dist_dir),
        "--buildpath", str(build_dir),
        "--noconfirm",
        "--clean",
    ]

    for src, dest in datas:
        args.extend(["--add-data", f"{src}{os.pathsep}{dest}"])

    for module in get_hidden_imports():
        args.extend(["--hidden-import", module])

    for src, dest in get_binaries():
        args.extend(["--add-binary", f"{src}{os.pathsep}{dest}"])

    args.extend(["--paths", str(project_root)])

    print("\nBuilding with PyInstaller...")
    try:
        PyInstaller.__main__.run(args)
        print("\n✓ Build completed successfully")
        return True
    except Exception as e:
        print(f"\n✗ Build failed: {e}")
        return False


def create_launcher_batch_file():
    project_root = get_project_root()
    dist_dir = project_root / "dist"
    launcher_path = dist_dir / "journiv.bat"

    batch_content = """@echo off
setlocal enabledelayedexpansion
set APP_DIR=%~dp0
if not exist "%APP_DIR%data" mkdir "%APP_DIR%data"
if not exist "%APP_DIR%data\\media" mkdir "%APP_DIR%data\\media"
"%APP_DIR%journiv.exe"
endlocal
"""
    try:
        launcher_path.write_text(batch_content)
        print(f"✓ Launcher batch file created")
    except Exception as e:
        print(f"Warning: Could not create launcher: {e}")


def create_readme():
    project_root = get_project_root()
    dist_dir = project_root / "dist"
    readme_path = dist_dir / "README.txt"

    readme_content = """╔════════════════════════════════════════════════════════════════╗
║           Journiv - Private Journal (Windows)                  ║
╚════════════════════════════════════════════════════════════════╝

QUICK START
===========
1. Extract this archive to any folder
2. Double-click "journiv.exe" or "journiv.bat"
3. Wait for the server to start (10-30 seconds on first run)
4. Your browser will open automatically
5. Create an account and start journaling!

REQUIREMENTS
============
- Windows 7 or later (64-bit)

DATA STORAGE
============
All your data is stored in:
  data/journiv.db (SQLite database)
  data/media/ (uploaded images, videos, etc.)

BACKUP
======
To backup, copy the "data" folder.

SUPPORT
=======
- Website: https://journiv.com
- GitHub: https://github.com/journiv/journiv-app
- Discord: https://discord.gg/CuEJ8qft46

LICENSE
=======
See https://github.com/journiv/journiv-app/blob/main/LICENSE.md
"""
    try:
        readme_path.write_text(readme_content)
        print(f"✓ README created")
    except Exception as e:
        print(f"Warning: Could not create README: {e}")


def main():
    print("=" * 70)
    print("Journiv Windows Executable Builder")
    print("=" * 70)

    if not setup_build_environment():
        return False

    if not build_executable():
        return False

    create_launcher_batch_file()
    create_readme()

    project_root = get_project_root()
    dist_dir = project_root / "dist"

    print("\n" + "=" * 70)
    print(f"✓ Build successful!")
    print(f"✓ Output: {dist_dir / 'journiv.exe'}")
    print("=" * 70)

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
