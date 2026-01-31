# Journiv Markdown to Quill Delta Migrator

A standalone Dart tool that converts Markdown content to Quill Delta JSON format for database migrations.

## Building

```bash
# Install dependencies
dart pub get

# Compile to native binary
dart compile exe migrator.dart -o migrator
```

The compiled `migrator` binary is platform-specific and not committed to git. It will be built automatically during Docker image builds.

## Usage

The migrator accepts Markdown content via **stdin only** and outputs Quill Delta JSON to stdout:

```bash
# Basic usage
echo "**Bold** text" | ./migrator

# From file
cat notes.md | ./migrator

# Process in pipeline
cat entry.md | ./migrator | jq .
```

### Command-line arguments are NOT supported

```bash
# ❌ This will fail
./migrator "**Bold** text"

# ✅ Use stdin instead
echo "**Bold** text" | ./migrator
```

## Exit Codes

- `0` - Success
- `1` - Invalid arguments
- `2` - Conversion error

## Features

- Converts GitHub-flavored Markdown to Quill Delta
- Supports custom `==highlight==` syntax
- Handles invalid Unicode gracefully
- Produces valid Quill Delta with required trailing newlines
- Strips media shortcodes during migration

## Testing

```bash
# From backend root directory
pytest tests/unit/test_dart_migrator.py -v
```
