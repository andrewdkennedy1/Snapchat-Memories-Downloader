# Free Snapchat Memories Downloader

**⚠️ Save your memories before Snapchat starts charging for storage!**

Download ALL your Snapchat memories completely FREE - don't pay for paid
services. This tool runs entirely on your computer, preserving all metadata
(dates, GPS locations) while keeping your data 100% private.

**Python GUI/CLI only:** Run the local Python app for full features and privacy.
Setup and usage are below.

## 📥 Getting Your Snapchat Data

Before using this tool, you need to download your data from Snapchat:

1. **Login** to [Snapchat's website](https://accounts.snapchat.com/)
2. Click the **menu** in the top left corner
   - **Mobile**: Tap "Accounts"
   - **Desktop**: Click "Account Settings"
3. Click **"My Data"**
4. Select the data you want to download:
   - ✅ **Memories** (required for this tool)
   - ✅ **Chat Media** (optional - now separate from Memories)
   - ✅ **Shared Stories** (optional - now separate from Memories)
   - Review all 8 types and select what you need
5. Click **"Submit Request"**
6. Wait for Snapchat to email you (can take 24-48 hours)
7. Download the ZIP file from the email
8. Extract it - you'll find `memories_history.html` in the `html/` folder

**Note:** Chat Media and Shared Stories used to be included with Memories,
but are now separate options at the bottom of the list.

[More info on Reddit](https://www.reddit.com/r/techsupport/comments/18mkfvv/is_there_a_way_of_exporting_all_snapchat/)

## Why Use This FREE Tool?

### 💰 Don't Pay for What Should Be Free

- **100% FREE** - Other services charge money. This costs nothing.
- **Save Before Fees** - Download now before Snapchat implements storage charges
- **Open Source** - Inspect the code yourself on GitHub

### 🔒 Privacy & Security

- **No Upload Required** - Your data never leaves your computer
- **Runs Locally** - Everything processes on your machine
- **No Account Needed** - No signup, no email, no tracking
- **Safer Than Paid Services** - Don't trust your memories to third-party servers

### ✨ Features

- Downloads all memories from `memories_history.html`
- Sequential naming: `01.jpg`, `02.mp4`, `03.jpg`, etc.
- **Timestamp-based filenames** (Python) - Name files as `YYYY.MM.DD-HH.MM.SS.ext` (Windows-safe) for easy sorting by date
- **Preserves ALL metadata**: dates, GPS coordinates, media type
- **Embeds EXIF metadata into images** - GPS coordinates and dates show up in Photos apps
- **Sets file timestamps to match original capture date**
- Handles ZIP files with overlays (extracts to `-main` and `-overlay` files)
- **Overlay merging** - Combine overlay on top of main content (images and videos)
  - Images: Fast, instant processing (supports JPG, PNG, WebP, GIF, BMP, TIFF)
  - Videos: Requires FFmpeg, may take 1-5 minutes per video
- **Merge existing files** - Retroactively merge already-downloaded `-main`/`-overlay` files without re-downloading
- **Duplicate detection** (Python) - Automatically find and remove duplicate files based on MD5 hash, filesize, and date
- **Multi-snap joining** (Python) - Automatically detect and concatenate videos taken within 10 seconds of each other
- Saves complete `metadata.json` with all information
- **Resume/Retry support** - Pick up where you left off or retry failed downloads
- Incremental metadata updates - Track download progress in real-time

## 🐍 Python Script

### Quick Start

```bash
# 1. Setup (one-time)
./setup.sh
source venv/bin/activate

# 2. Download your memories
python app.py

# 3. Done! Files saved to ./memories/
```

### Setup

1. Run the setup script:

   ```bash
   ./setup.sh
   ```

   This creates a virtual environment and installs dependencies.

2. **(Optional)** Install FFmpeg for video overlay merging:

   | Platform              | Command                                                      |
   |-----------------------|--------------------------------------------------------------|
   | macOS                 | `brew install ffmpeg`                                        |
   | Ubuntu/Debian         | `sudo apt-get install ffmpeg`                                |
   | Windows (Chocolatey)  | `choco install ffmpeg`                                       |
   | Windows (manual)      | Download from [ffmpeg.org](https://ffmpeg.org/download.html) |

   **Note:** FFmpeg is only needed for merging video overlays.
   Without it, videos are saved as separate `-main` and `-overlay` files.

### Basic Usage

**Activate environment** (do this each time you open a new terminal):

```bash
source venv/bin/activate
```

**Test mode** (download first 3 files only):

```bash
python app.py --test
```

**Full download**:

```bash
python app.py
```

**Custom HTML file path**:

```bash
# Direct file path
python app.py /path/to/memories_history.html

# Or folder containing the HTML
python app.py /path/to/html/folder
```

**Resume/Retry**:

```bash
# Resume interrupted download
python app.py --resume

# Retry only failed downloads
python app.py --retry-failed
```

### Advanced Features

#### Merge Overlays

Combine overlay files with main content:

```bash
python app.py --merge-overlays
```

- **Images:** Fast, instant processing
- **Videos:** Requires FFmpeg, 1-5 minutes per video

**Re-process specific media type:**

```bash
# Videos only
python app.py --videos-only --merge-overlays

# Pictures only
python app.py --pictures-only --merge-overlays
```

**Merge already-downloaded files:**

```bash
python app.py --merge-existing ./memories
```

Creates merged versions without deleting originals.

#### Custom Output Directory

```bash
python app.py -o /path/to/output
```

Saves files to a custom location instead of `./memories/`

#### Timestamp-Based Filenames

```bash
python app.py --timestamp-filenames
```

Names files as `2024.11.30-14.30.45.jpg` instead of `01.jpg`

- ✅ Files sort by date in file managers
- ✅ Easy to identify when memories were taken

#### Remove Duplicate Files

```bash
python app.py --remove-duplicates
```

Checks MD5 hash before saving each file and skips duplicates.

- ✅ Saves bandwidth - doesn't re-download existing files
- ✅ Perfect for resuming or re-running the script
- ✅ Handles cases where Snapchat exports the same memory multiple times

#### Join Multi-Snap Videos

```bash
python app.py --join-multi-snaps
```

Detects videos taken within 10 seconds and concatenates them.

- ✅ Stitches long stories back together
- ✅ Requires FFmpeg
- ✅ Deletes originals after successful join

### Combining Features

```bash
# All the features!
python app.py \
  -o ~/Desktop/memories \
  --timestamp-filenames \
  --remove-duplicates \
  --merge-overlays \
  --join-multi-snaps

# Resume with duplicate detection
python app.py --resume --remove-duplicates
```

### Getting Help

```bash
# View all options
python app.py --help

# When done, deactivate virtual environment
deactivate
```

## Output

### Files

- All memories are saved to the `memories/` directory (or custom directory specified with `--output`)
- **Sequential naming (default)**: `01.jpg`, `02.mp4`, `03.jpg`, etc.
- **Timestamp naming (with `--timestamp-filenames`)**: `2024.11.30-14.30.45.jpg`, `2024.12.15-09.22.13.mp4`, etc.
- Files with overlays are extracted as `XX-main.ext` and `XX-overlay.ext` (or `YYYY.MM.DD-HH.MM.SS-main.ext` with timestamp naming)

### Metadata

A `metadata.json` file is created with information about each memory:

```json
{
  "number": 1,
  "date": "2025-11-30 00:31:09 UTC",
  "media_type": "Video",
  "latitude": "44.273846",
  "longitude": "-105.43944",
  "url": "https://...",
  "status": "success",
  "files": [
    {
      "path": "01.mp4",
      "size": 4884414,
      "type": "single"
    }
  ]
}
```

For memories with overlays (not merged):

```json
{
  "number": 42,
  "date": "2024-06-15 14:30:00 UTC",
  "media_type": "Image",
  "latitude": "40.7128",
  "longitude": "-74.0060",
  "url": "https://...",
  "status": "success",
  "files": [
    {
      "path": "42-main.jpg",
      "size": 450123,
      "type": "main"
    },
    {
      "path": "42-overlay.jpg",
      "size": 125456,
      "type": "overlay"
    }
  ]
}
```

For merged overlays (when using `--merge-overlays` flag):

```json
{
  "number": 42,
  "date": "2024-06-15 14:30:00 UTC",
  "media_type": "Image",
  "latitude": "40.7128",
  "longitude": "-74.0060",
  "url": "https://...",
  "status": "success",
  "files": [
    {
      "path": "42.jpg",
      "size": 487932,
      "type": "merged"
    }
  ]
}
```

## Requirements

- Python 3.7+
- `requests` library (installed automatically by setup.sh)
- `Pillow` library (for overlay merging and EXIF metadata, installed automatically by setup.sh)
- `piexif` library (for EXIF metadata embedding, installed automatically by setup.sh)

## File Structure

```text
.
├── html/
│   └── memories_history.html    # Snapchat export HTML file (not included)
├── memories/                     # Downloaded files (default output directory, created by script)
│   ├── 01.mp4                    # Sequential naming (default)
│   ├── 02.jpg                    # or 2024.11.30-14.30.45.jpg (with --timestamp-filenames)
│   ├── 03.jpg
│   └── metadata.json
├── snapchat_memories_downloader/ # Modular Python implementation
│   ├── __init__.py               # Package exports
│   ├── orchestrator.py           # Main download orchestration
│   ├── parser.py                 # HTML parsing logic
│   ├── downloader.py             # Core download functionality
│   ├── files.py                  # File operations and naming
│   ├── metadata_store.py         # Metadata persistence
│   ├── overlay.py                # Overlay merging (images/videos)
│   ├── exif_utils.py             # EXIF metadata handling
│   ├── duplicates.py             # Duplicate detection
│   ├── multisnap.py              # Multi-snap video joining
│   └── merge_existing.py         # Retroactive overlay merging
├── tests/                        # Test files and fixtures
├── venv/                        # Python virtual environment
├── app.py                       # Python GUI/CLI entrypoint
├── requirements.txt             # Python dependencies
├── setup.sh                     # Setup script
├── .gitignore                   # Git ignore file
└── README.md                    # This file
```

## How Resume/Retry Works

### Python Script

1. **First Run**: Creates `metadata.json` with all memories marked as "pending"
2. **During Download**: Updates each item to "in_progress" → "success" or "failed"
3. **Interrupted?** Run with `--resume` to continue from where you left off
4. **Failures?** Run with `--retry-failed` to retry only failed items

The metadata.json is saved after EACH download, so you can safely interrupt
and resume at any time!

## Notes

- Downloads may take a while depending on file sizes and internet speed
- Failed downloads are logged in the metadata with error messages
- The script uses sequential numbering starting from 01
- **File timestamps are set to match the original capture date**, so when you
  sort by date modified in Finder/Explorer, you'll see them in chronological
  order by when they were taken, not when they were downloaded

---

## 🔐 How Your Data Stays Private

- **Python Script**: Everything runs locally on your computer. No network
  requests except to Snapchat's download URLs.
- Your memories are downloaded directly from Snapchat's servers using the URLs
  in your data export.

---

## ☕ Support

If this tool helped you recover your memories, consider [buying me a coffee](https://buymeacoffee.com/andrefecto)!

---

## 🔧 Troubleshooting

### Videos Download as Blank/Black Files

If your videos are downloading but show as blank or black when you try to play them:

**Cause:** The download URLs from Snapchat may have expired,
or the server is returning error pages instead of video files.

**How to tell:**

- The tool will show warnings like:
  `WARNING: File may not be a valid video (invalid MP4 signature)`
- Very small file sizes (under 100 bytes) indicate invalid files
- The log will show the first bytes of the file to help diagnose the issue

**Solutions:**

1. **Request a fresh data export from Snapchat**
   - URLs expire after some time
2. **Download sooner**
   - Process your Snapchat export as soon as you receive it
3. **Check the warnings**
   - The tool will alert you to potentially invalid files during download

**Note:** The tool validates video files and warns you about potential issues,
but it cannot fix expired or invalid URLs from Snapchat's servers.

### FFmpeg Not Found (Python)

If you see: `Warning: ffmpeg not found. Video overlay merging will be disabled.`

**Solution:** Install FFmpeg:

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Windows**: `choco install ffmpeg` or download from
  [ffmpeg.org](https://ffmpeg.org/download.html)

The tool will still work without FFmpeg - videos will be saved as separate
`-main` and `-overlay` files.

### FFmpeg Merge Fails (Video Overlays)

If video overlay merging fails with `Conversion failed!`:

- Make sure your FFmpeg build includes the `libx264` video encoder.
- Some videos may have audio codecs that can’t be stream-copied into MP4; the downloader will retry by re-encoding audio to AAC.
- If it still fails, the tool will keep the separate `-main`/`-overlay` files so you can merge later.

## 📄 License

MIT License - feel free to use and modify as needed.

## 🤝 Contributing

Issues and pull requests are welcome!

---

**Made by [@andrefecto](https://github.com/andrefecto)**
