# Windows Installation & Build Guide

## For End Users - Running the Executable

### Quick Start (Easiest)

1. Download the latest `journiv-windows-*.zip` from [Releases](https://github.com/journiv/journiv-app/releases)
2. Extract the ZIP file to any folder
3. Double-click `journiv.exe` or `journiv.bat`
4. Wait 10-30 seconds on first run (it will set up automatically)
5. Your browser will open automatically - create an account and start journaling!

### First Run Behavior

On the first run:
- The app creates a configuration file (`.env`)
- A SQLite database is initialized in the `data` folder
- A browser opens automatically to `http://localhost:8000`
- You can create a new account immediately

### Subsequent Runs

Just double-click `journiv.exe` or `journiv.bat` again.

### System Requirements

- Windows 7 or later (64-bit)
- No additional software needed
- Internet access recommended (for features like export, OAuth, etc.)

### Where Is My Data?

All your journal entries are stored locally in:
- `data/journiv.db` - SQLite database with all journal entries
- `data/media/` - Uploaded images, videos, and other media files

### How to Back Up

Simply copy the `data` folder to another location.

### Troubleshooting

**The app won't start:**
- Check that you have administrator permissions
- Try running as administrator (right-click `journiv.bat`, select "Run as administrator")
- Check the console window for error messages

**Port 8000 is in use:**
- The app will automatically find another available port (8001, 8002, etc.)
- The browser should still open to the correct URL

**Can't find the browser:**
- The browser may open behind other windows
- Check your taskbar or try clicking back to the Journiv window

---

## For Developers - Building the Executable

### Prerequisites

- Windows 10+ or WSL2
- Python 3.12 or later
- Git
- pip (comes with Python)

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/journiv/journiv-app.git
cd journiv-app

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -e .

# Install build dependencies
pip install pyinstaller
```

### Building the Executable

```bash
# Build the executable
python scripts/build_executable.py
```

This creates:
- `dist/journiv.exe` - The standalone executable
- `dist/journiv.bat` - Batch file launcher
- `dist/README.txt` - User instructions

### Build Options

You can modify `scripts/build_executable.py` to customize:
- Icon (set `--icon` parameter)
- Included data files
- Hidden imports
- Console window behavior (windowed vs console)

### Creating an Installer (Optional)

To create a proper Windows installer, use NSIS:

```bash
# Install NSIS
choco install nsis

# Use the installer script (coming soon)
```

### Distributing the Build

1. The entire `dist` folder can be zipped and distributed
2. Users just extract and run `journiv.exe`
3. Or create a release on GitHub with the zip file

### Testing the Build

```bash
# Run the built executable
dist\journiv.exe

# Or use the batch launcher
dist\journiv.bat
```

---

## Automating Builds with GitHub Actions

The `.github/workflows/build-windows-exe.yml` workflow automatically:

1. Builds Windows executables on every tag push (v*.*.*)
2. Creates a ZIP distribution
3. Uploads to GitHub Releases
4. Includes installation instructions

To trigger a build:

```bash
# Create and push a tag
git tag -a v0.1.0-beta.23 -m "Release with Windows executable"
git push origin v0.1.0-beta.23
```

The workflow will automatically build and release!

---

## Advanced Configuration

### Custom Port

Modify the launcher script or use environment variable:
```batch
set PORT=9000
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
```

### Production Deployment

For production use:
- Set `ENVIRONMENT=production`
- Use a reverse proxy (nginx, IIS)
- Enable HTTPS with proper certificates
- Configure database to PostgreSQL
- Set proper `SECRET_KEY` and `DOMAIN_NAME`

---

## Troubleshooting Build Issues

**PyInstaller errors:**
- Make sure all dependencies are installed: `pip install -e .`
- Try cleaning: `python scripts/build_executable.py` (includes cleanup)

**Missing modules:**
- Check `hidden-import` list in `build_executable.py`
- Run `pip list` to verify dependencies

**File size too large:**
- This is normal for a bundled Python + all dependencies
- Typical size: 150-300MB

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/journiv/journiv-app/issues
- Discord: https://discord.gg/CuEJ8qft46
- Email: journiv@protonmail.com
