import secrets
from pathlib import Path


def generate_secret_key():
    return secrets.token_urlsafe(32)


def setup_default_env(app_root: Path):
    env_file = app_root / ".env"
    if env_file.exists():
        return True

    secret_key = generate_secret_key()
    env_content = f"""SECRET_KEY={secret_key}
DOMAIN_NAME=localhost:8000
DB_DRIVER=sqlite
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=info
MEDIA_ROOT=/data/media
ENABLE_CORS=false
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
"""
    try:
        env_file.write_text(env_content)
        print(f"Created default configuration at {env_file}")
        return True
    except Exception as e:
        print(f"Error creating .env file: {e}")
        return False


def ensure_data_directories(app_root: Path):
    for directory in [app_root / "data", app_root / "data" / "media"]:
        directory.mkdir(parents=True, exist_ok=True)
    return True


def main():
    app_root = Path(__file__).parent.parent.resolve()
    print("Setting up Journiv for standalone execution...")

    if not ensure_data_directories(app_root):
        print("Failed to create data directories")
        return False

    if not setup_default_env(app_root):
        print("Failed to create configuration")
        return False

    print("Setup complete!")
    return True


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
