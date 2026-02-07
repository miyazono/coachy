# Privacy

Coachy is a local-first productivity tool. This document explains exactly what data it collects, where that data goes, and how to control it.

## What Gets Captured

Every `interval_seconds` (default: 60s), the daemon captures:

- **Full-screen screenshot** (JPEG) of your primary display
- **Active window info**: app name, window title, bundle ID
- **OCR text**: text extracted from the screenshot using macOS Vision framework
- **Activity classification**: a category label (e.g., `deep_work`, `communication`) derived from app name and window title

## What Stays on Your Machine (Always)

The following data **never** leaves your computer:

- Screenshots (stored in `data/screenshots/`, auto-deleted by retention policy)
- OCR text (stored in SQLite database)
- Raw window titles and app names in the database
- All log files

Files are stored with owner-only permissions (`0o600`).

## What Gets Sent to the LLM API

When you run `coachy digest`, an activity summary is sent to the configured LLM provider (Anthropic by default). The `privacy_level` setting in `config.yaml` controls how much detail is included:

### `privacy_level: "private"` (default)

Only aggregated categories are sent. The API sees:

- Category durations (e.g., "deep_work: 240 min (42%)")
- Hourly timeline with category labels only
- Total tracked time
- Your priorities (from `priorities.md`)

The API does **not** see: app names, window titles, file paths, project names, or OCR text.

### `privacy_level: "detailed"`

Includes everything in "private" mode, plus:

- App names with durations (e.g., "VS Code: 240 minutes")
- Window title context for productive sessions (e.g., "VS Code (main.py - myproject): 240 min")

### Overriding per-invocation

Use the `--privacy` flag to override for a single digest:

```bash
coachy digest --privacy detailed  # full context this time only
coachy digest --privacy private   # categories only
```

## Using a Local LLM (Zero Network Calls)

Set `coach.llm_provider` to `"local"` or `"mlx"` in `config.yaml` to route digest generation through a local model. When using a local LLM, **no data leaves your machine at all** — not even aggregated summaries.

## Data Retention

- **Default retention**: 30 days (configurable via `storage.retention_days`)
- **Auto-cleanup**: the daemon automatically deletes data older than the retention period once per hour
- **Manual cleanup**: `coachy cleanup` or `coachy cleanup --days 7`
- **Full wipe**: `coachy wipe --confirm` deletes all screenshots, the database, and log files

## Excluding Apps and Windows

Sensitive apps can be excluded from capture entirely via `config.yaml`:

```yaml
capture:
  excluded_apps:
    - "1Password"
    - "Zoom"
    - "FaceTime"
  excluded_titles:
    - "private"
    - "incognito"
```

Excluded apps are logged as `excluded` in the database (for time tracking) but no screenshot is taken and no OCR is performed.

## Telemetry

None. Zero. Coachy makes no network calls except when you explicitly run `coachy digest` with a cloud LLM provider. There is no analytics, no crash reporting, no update checks, no phoning home.

## File Permissions

All data files (database, screenshots, logs) are created with `0o600` permissions (owner read/write only).

## Source of Truth

This document describes the behavior of the code in this repository. If in doubt, read the source — the relevant files are:

- `coachy/capture/daemon.py` — what gets captured and when
- `coachy/coach/digest.py` — what gets sent to the LLM (`_format_activity_for_prompt`)
- `coachy/config.py` — privacy_level configuration
- `coachy/storage/db.py` — what gets stored locally
