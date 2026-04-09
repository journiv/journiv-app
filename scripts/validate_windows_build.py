import sys
from pathlib import Path


def check_file_exists(path: Path, desc: str):
    if path.exists():
        print(f"✓ {desc}: {path.name}")
        return True
    else:
        print(f"✗ {desc}: NOT FOUND")
        return False


def check_directory_exists(path: Path, desc: str):
    if path.exists() and path.is_dir():
        print(f"✓ {desc}: {path.name}")
        return True
    else:
        print(f"✗ {desc}: NOT FOUND")
        return False


def check_python_version():
    info = sys.version_info
    if info.major >= 3 and info.minor >= 12:
        print(f"✓ Python: {info.major}.{info.minor}")
        return True
    else:
        print(f"✗ Python {info.major}.{info.minor} - need 3.12+")
        return False


def check_dependencies():
    required = ["fastapi", "uvicorn", "pydantic", "sqlmodel", "sqlalchemy"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
            print(f"✓ {pkg}")
        except ImportError:
            print(f"✗ {pkg}")
            missing.append(pkg)

    return len(missing) == 0, missing


def main():
    print("=" * 70)
    print("Journiv Windows Build - Validation Check")
    print("=" * 70)
    print()

    app_root = Path(__file__).parent.parent.resolve()
    all_ok = True

    print("Python Check:")
    if not check_python_version():
        all_ok = False
    print()

    print("Build Files:")
    files = [
        (app_root / "scripts" / "build_executable.py", "Build script"),
        (app_root / "scripts" / "setup_defaults.py", "Setup script"),
        (app_root / "scripts" / "run.bat", "Launcher"),
        (app_root / ".github" / "workflows" / "build-windows-exe.yml", "GitHub workflow"),
        (app_root / "WINDOWS_GUIDE.md", "Guide"),
        (app_root / "app" / "main.py", "FastAPI app"),
        (app_root / "pyproject.toml", "Config"),
    ]

    for fpath, desc in files:
        if not check_file_exists(fpath, desc):
            all_ok = False

    print()
    print("Directories:")
    dirs = [
        (app_root / "app", "app/"),
        (app_root / "scripts", "scripts/"),
        (app_root / ".github" / "workflows", "workflows/"),
    ]

    for dpath, desc in dirs:
        if not check_directory_exists(dpath, desc):
            all_ok = False

    print()
    print("Python Dependencies:")
    deps_ok, missing = check_dependencies()
    if not deps_ok:
        all_ok = False

    print()
    print("=" * 70)
    if all_ok:
        print("✓ Ready to build!")
        print()
        print("Next steps:")
        print("  pip install pyinstaller")
        print("  python scripts/build_executable.py")
        print()
    else:
        print("✗ Fix issues above")
        return False

    print("=" * 70)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
