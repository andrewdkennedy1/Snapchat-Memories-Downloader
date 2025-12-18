# AGENTS.md

This file provides guidance to LLM Programming agents when working with code in this repository.

## Project Overview

Python-only Snapchat Memories downloader that parses `memories_history.html` exports to download media with metadata preservation.

**Python Version**: `app.py` - GUI/CLI entrypoint with modular implementation in `snapchat_memories_downloader/`

## Code Architecture Principles

**Maintain modular design - avoid monolithic files:**

- **Single Responsibility**: Each module handles one concern (parsing, downloading, EXIF, etc.)
- **Small Functions**: Keep functions under 50 lines, extract complex logic into helpers
- **Clear Interfaces**: Use type hints and docstrings for module boundaries
- **Dependency Injection**: Pass dependencies as parameters rather than importing globally
- **Separation of Concerns**: Keep I/O, business logic, and presentation separate

**When adding features:**
- Create new modules for distinct functionality
- Extract shared utilities to separate files
- Avoid adding to existing large functions - refactor into smaller pieces
- Use composition over inheritance

**File size guidelines:**
- Modules should stay under 500 lines
- If a module grows beyond this, split by logical boundaries
- Extract constants, utilities, and data structures to separate files

## Development Commands

### Python Setup
```bash
./setup.sh                    # Create venv, install dependencies
source venv/bin/activate      # Activate environment
python3 app.py --test  # Quick test (first 3 files)
deactivate                    # Exit venv
```

### Common Python Usage
```bash
# Basic download
python3 app.py

# Resume interrupted download
python3 app.py --resume

# Retry only failed items
python3 app.py --retry-failed

# Merge overlays (requires FFmpeg for videos)
python3 app.py --merge-overlays

# Timestamp-based naming instead of sequential
python3 app.py --timestamp-filenames

# Process only videos with overlay merging
python3 app.py --videos-only --merge-overlays

# Custom output directory
python3 app.py -o ./my-memories
```

## Core Architecture

### Data Flow
1. Parse `memories_history.html` → extract URLs, dates, GPS coordinates
2. Initialize metadata.json with all memories as "pending"
3. For each memory:
   - Download from Snapchat URL
   - Detect ZIP files (magic bytes `PK`) containing overlays
   - Check MD5 hash for duplicates (during download, not post-process)
   - Extract `-main` and `-overlay` files from ZIP or save single file
   - Add EXIF metadata to images (GPS + timestamp)
   - Optionally merge overlays (instant for images, 1-5min for videos)
   - Set file modification time to capture date
   - Update metadata state: `pending` → `in_progress` → `success`/`failed`
4. Optional post-processing: join multi-snap videos, deduplicate

### Metadata State Machine
`metadata.json` tracks download progress enabling crash recovery:
- **States**: `pending`, `in_progress`, `success`, `failed`, `skipped`
- **Saved after every download** for resume capability
- Stores file paths, sizes, types (main/overlay/merged/single/duplicate)

### Overlay Processing Architecture

**Two strategies based on media type:**

**Images** (fast, instant):
- Python: Pillow library for alpha compositing
- Preserves original format (JPEG, PNG, WebP, GIF, BMP, TIFF)

**Videos** (slow, 1-5 minutes each):
- Python: FFmpeg subprocess with filter chains
- FFmpeg filter: `[1:v]scale=WxH[ovr];[0:v][ovr]overlay=shortest=1[outv]`
- Handles both image overlays (with `-loop 1`) and video overlays

**Deferred Processing Pattern** (`--defer-video-overlays`):
- Downloads all content first (main + overlay files saved separately)
- Processes video merges at end in batch
- Prevents memory buildup during initial downloads

### Duplicate Detection
Runs **during download** (not post-processing) to save bandwidth:
1. Check file size match
2. Compute MD5 hash of new download
3. Compare with existing files
4. Skip download if duplicate found

Python also has `--remove-duplicates` for retroactive scanning.

### Multi-Snap Joining (Python Only)
Detects videos within 10-second time windows (indicates multi-snap stories):
- Uses FFmpeg concat demuxer: `-f concat -safe 0 -i concat.txt -c copy`
- No re-encoding (fast, lossless)
- Deletes originals after successful join

## Key Technologies

**Python Dependencies**:
- `requests` - HTTP downloads with custom User-Agent
- `Pillow` - Image overlay compositing, format preservation
- `piexif` - EXIF metadata encoding (GPS + dates in JPEG/PNG/WebP)
- `subprocess` - FFmpeg process invocation
- `zipfile` - Extract overlay ZIP files
- `hashlib` - MD5 for duplicate detection

## File Structure

```
.
├── app.py                   # Python GUI/CLI entrypoint
├── snapchat_memories_downloader/  # Modular Python implementation
│   ├── __init__.py           # Package exports
│   ├── orchestrator.py       # Main download orchestration
│   ├── parser.py             # HTML parsing logic
│   ├── downloader.py         # Core download functionality
│   ├── files.py              # File operations and naming
│   ├── metadata_store.py     # Metadata persistence
│   ├── overlay.py            # Overlay merging (images/videos)
│   ├── exif_utils.py         # EXIF metadata handling
│   ├── duplicates.py         # Duplicate detection
│   ├── multisnap.py          # Multi-snap video joining
│   ├── merge_existing.py     # Retroactive overlay merging
│   └── deps.py               # Dependency management
├── tests/                    # Test files and fixtures
├── requirements.txt          # Python dependencies
├── setup.sh                  # Venv setup script
└── README.md                 # Project documentation
```

## Non-Obvious Implementation Details

### Magic Byte Detection
The downloader detects file types by reading first bytes, not trusting extensions/MIME:
- ZIP: `50 4B` (PK)
- JPEG: `FF D8 FF`
- PNG: `89 50 4E 47`
- WebP: `52 49 46 46 ... 57 45 42 50`
- GIF: `47 49 46 38`
- MP4: `66 74 79 70` at offset 4 (ftyp box)

### EXIF Coordinate Conversion
GPS coordinates converted from decimal to DMS (degrees, minutes, seconds):
```python
def decimal_to_dms(decimal):
    degrees = int(abs(decimal))
    minutes_float = (abs(decimal) - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    return ((degrees, 1), (minutes, 1), (int(seconds * 100), 100))
```

### Graceful Degradation
All optional dependencies degrade gracefully:
- No FFmpeg → videos save as separate `-main`/`-overlay` files
- No Pillow → overlay merging disabled
- No piexif → EXIF metadata skipped
- Never fails due to missing optional features

### File Timestamp Preservation
The downloader sets file modification time to Snapchat capture date:
- Python: `os.utime(filepath, (timestamp, timestamp))`

Enables sorting by capture date in file explorers.

## Testing

**Python Quick Test**:
```bash
python3 app.py --test  # Downloads first 3 files only
```

**Validation Features**:
- MP4 signature validation (checks for ftyp/mdat/moov/wide magic bytes)
- File size warnings (< 100 bytes indicates invalid/expired URL)
- EXIF metadata verification

## Common Pitfalls

1. **Expired URLs**: Snapchat URLs expire after ~1 year, validate file size and magic bytes
2. **Multi-snap detection**: 10-second threshold is empirically derived, may need tuning

## Privacy Architecture

**Local processing** ensures privacy:
- All processing on local machine
- No tracking, no analytics, no external API calls
- Open source for audit
