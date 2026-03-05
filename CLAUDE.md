# Coachy Development Context

## What This Project Is
Coachy is a local-first productivity monitoring and coaching system. It captures periodic screenshots, extracts activity context, and generates coaching digests using configurable AI personas.

## Key Design Constraints
1. **Privacy-first**: All capture and processing happens locally. Only aggregated summaries go to external LLMs (controlled by `privacy_level` setting). See PRIVACY.md.
2. **Token-efficient**: Use local OCR/classification. Target <5k tokens/day for digests.
3. **macOS-focused**: Use native frameworks (Vision, Quartz, AppKit) for performance.

## Environment
- **Python Version**: 3.9.6
- **Platform**: macOS (required for Vision/Quartz frameworks)
- **Key Dependencies**: anthropic, click, pyyaml, pyobjc frameworks

## File Structure
```
coachy/
├── coachy/                    # Main package
│   ├── __init__.py
│   ├── cli.py                # Click CLI with all commands
│   ├── config.py             # YAML configuration management
│   ├── capture/              # Screenshot & window detection
│   │   ├── daemon.py         # Background capture process
│   │   ├── screenshot.py     # Quartz-based capture
│   │   ├── window.py         # AppKit window detection
│   │   └── windows.py        # CGWindowList visible window enumeration
│   ├── process/              # Activity processing
│   │   ├── ocr.py           # Vision framework OCR (flat + bounding-box)
│   │   ├── spatial.py        # Map OCR blocks to windows
│   │   ├── classifier.py     # Rules-based categorization
│   │   └── pipeline.py       # Processing orchestration
│   ├── storage/              # Data persistence
│   │   ├── db.py            # SQLite operations
│   │   └── models.py        # Data models & schema
│   └── coach/               # Coaching system
│       ├── digest.py        # Digest generation (uses block builder + scrubber)
│       ├── blocks.py        # Activity Block Builder & Formatter (Phase 7)
│       ├── privacy_scrubber.py  # Local privacy scrubbing before cloud API
│       ├── llm.py          # Anthropic API client
│       ├── priorities.py    # Priorities parser
│       └── personas.py      # Coach persona manager
├── personas/                 # Public coach personality files
│   └── grove.md             # Andy Grove - High Output Management (default)
├── private-personas/         # Private personas (gitignored, loaded automatically)
├── data/                     # Runtime data (gitignored)
│   ├── screenshots/          # Captured images
│   ├── coachy.db            # SQLite database
│   └── logs/                # Application logs
├── config.yaml.example      # Example config (copied to config.yaml on first run)
├── config.yaml              # User configuration (gitignored)
├── priorities.md.example    # Example priorities template
├── priorities.md            # User's current priorities (gitignored)
├── scrubber_prompt.md.example  # Default privacy scrubber prompt template
├── PRIVACY.md               # Data flow and privacy documentation
└── pyproject.toml           # Dependencies & build config
```

## Current Status

### ✅ Phase 1: Foundation (Complete)
- Screenshot capture with Quartz framework
- Window detection with AppKit
- SQLite storage with activity logging
- Background daemon process
- Basic CLI interface

### ✅ Phase 2: Processing Pipeline (Complete)
- OCR with Vision framework (ready, needs macOS deps)
- Rules-based activity classifier (8 categories)
- Processing pipeline integration
- Enhanced CLI with stats and categories

### ✅ Phase 3: Basic Digest (Complete)
- Activity aggregation with timeline & productivity metrics
- Priorities loading from markdown
- Anthropic API integration
- Digest generation with Andy Grove persona
- CLI digest command

### ✅ Phase 4: Coach Personas (Complete)
- Four distinct coaching personas implemented
- Persona management system with validation
- CLI coaches command
- Different coaching styles per persona

### ✅ Phase 5: Polish, Reliability, and Privacy Hardening (Complete)
- Configurable privacy levels (`private`/`detailed`) for API prompts
- Personal files gitignored (config.yaml, priorities.md) with .example templates
- File permissions (0o600) on database, screenshots, and logs
- Log rotation (5MB, 3 backups) via RotatingFileHandler
- Hourly auto-cleanup in daemon with WAL checkpoint
- Startup validation (writable dirs, disk space check)
- Tightened exception handling across daemon, window, and LLM modules
- `wipe --confirm` command for full data deletion

### ✅ Phase 6: Spatial Window-Aware OCR (Complete)
- Window enumeration via CGWindowListCopyWindowInfo (`coachy/capture/windows.py`)
- Bounding-box OCR preserving Vision coordinates (`extract_text_blocks()` in `ocr.py`)
- Spatial mapping of OCR blocks to windows (`coachy/process/spatial.py`)
- Pipeline integration with fallback to basic OCR (`pipeline.py`)
- Per-window change detection in diff engine (`diff.py`)
- Workspace context (layouts, focus patterns, reference materials) in digests
- Window metadata stored in `activity_log.metadata["windows"]`
- 15 unit tests covering coordinate math, window matching, and serialization
- Graceful double-stop handling
- Fixed excluded_minutes query, Vision framework object cleanup
- PRIVACY.md documenting full data flow

### ✅ Phase 7: Activity Block Builder & Privacy Scrubber (Complete)
- **Problem solved:** Old pipeline crushed rich OCR data into 8 rigid categories. The LLM coach received "deep_work: 454 min" when the user actually had specific emails, meetings, and doc editing sessions.
- **Activity Block Builder** (`coachy/coach/blocks.py`): Converts raw DB captures into grouped activity blocks with 5-stage pipeline:
  1. Identify active window per capture (using per-window change ratios, not just OS-reported focus)
  2. Group consecutive captures with same active window into blocks
  3. Build ActivityBlock objects with context extraction (email subjects, chat channels, editor filenames, browser page titles)
  4. Merge related blocks across brief (<3min) interruptions
  5. Compute timeline-level stats
- **Rich output per block:** app name, activity label, duration, engagement level, creation/consumption mode, background apps, full OCR content from all captures (deduplicated)
- **Formatter features:**
  - No block cap — full day comes through (~350 blocks, ~38k tokens, ~19% of Sonnet's 200k context)
  - Short-block compression: 3+ consecutive ≤2min blocks on the same app collapse into `[N quick views]` summary lines
  - OCR incoherence detection: garbled OCR segments (e.g., `sf8G`, `BERGCHI`) replaced with `<<incoherent>>`, consecutive markers collapsed
- **Video call inference:** Blocks where the active app is "Other" (window not in spatial map) are analyzed via OCR patterns to detect video calls, extracting participant names when possible
- **Video call apps removed from default excluded_apps:** OCR only captures text, not faces — safe to include Zoom, Meet, Teams, etc.
- **Browser classifier fix:** Browsers now classified by window title content (gmail→communication, github→deep_work, twitter→social_media) instead of all browsers→"research"
- **Privacy Scrubber** (`coachy/coach/privacy_scrubber.py`): Runs locally before any data goes to the cloud API. Supports MLX, local OpenAI-compat, or regex-only mode. User-editable prompt at `~/Library/Application Support/Coachy/scrubber_prompt.md`
- **Digest pipeline rewired:** `digest.py` now builds block timeline → scrubs → sends to cloud. `privacy_level: "private"` is a kill switch that falls back to category-only output.
- CLI: `scrubber-prompt` command, `--raw` flag on `digest`
- Config: `privacy.scrubber_enabled`, `privacy.scrubber_model`, `privacy.scrubber_prompt_path`
- 34 unit tests in `test_blocks.py`

## CLI Commands

**Core Operations:**
- `python3 -m coachy.cli start` - Start capture daemon
- `python3 -m coachy.cli stop` - Stop capture daemon
- `python3 -m coachy.cli status` - Check status & stats

**Coaching:**
- `python3 -m coachy.cli digest` - Generate coaching digest
- `python3 -m coachy.cli digest --coach huang` - Use specific coach
- `python3 -m coachy.cli digest --period week` - Weekly digest
- `python3 -m coachy.cli digest --privacy detailed` - Override privacy level
- `python3 -m coachy.cli digest --raw` - Show pre-scrub vs post-scrub output
- `python3 -m coachy.cli coaches` - List available coaches

**Configuration:**
- `python3 -m coachy.cli configure` - Edit config.yaml
- `python3 -m coachy.cli priorities` - Edit priorities.md
- `python3 -m coachy.cli scrubber-prompt` - Edit privacy scrubber prompt
- `python3 -m coachy.cli categories` - Show activity categories

**Maintenance:**
- `python3 -m coachy.cli cleanup` - Clean old data
- `python3 -m coachy.cli wipe --confirm` - Delete ALL data (screenshots, DB, logs)
- `python3 -m coachy.cli stats` - Detailed statistics

**Testing:**
- `python3 -m coachy.cli test --test-classifier` - Test classifier
- `python3 -m coachy.cli test --test-ocr` - Test OCR

## Testing

Run phase-specific test suites:
```bash
python3 test_basic.py    # Phase 1 foundation tests
python3 test_phase2.py   # Processing pipeline tests
python3 test_phase3.py   # Digest generation tests
python3 test_phase4.py   # Coach personas tests
python3 -m unittest test_spatial -v  # Phase 6 spatial OCR tests
python3 -m unittest test_blocks -v   # Phase 7 block builder + scrubber tests
```

## Digest Pipeline Architecture

The digest pipeline converts raw screen captures into coaching-ready text:

```
DB captures → ActivityBlockBuilder → ActivityTimeline → PrivacyScrubber → Cloud LLM
```

**Data flow (in `coach/digest.py`):**
1. `get_activity_metadata_timeline(start, end)` fetches rows from DB (omits large `ocr_text` column; per-window OCR is in `metadata["windows"]`)
2. `ActivityBlockBuilder.build_timeline(rows)` groups captures into `ActivityBlock` objects:
   - Each block = contiguous activity on one app/window
   - Includes: app name, activity label, duration, engagement, mode (creating/consuming/mixed), background apps, full OCR content
   - "Other" blocks are analyzed via OCR patterns to detect video calls
3. `ActivityBlockFormatter.format_for_prompt(timeline)` produces markdown text (~38k tokens for a full day, ~19% of Sonnet's 200k context). No block cap — all blocks included. Consecutive short blocks on the same app are compressed into `[N quick views]` summary lines. Garbled OCR segments are replaced with `<<incoherent>>`.
4. `PrivacyScrubber.scrub(text)` anonymizes PII locally (regex mode by default; MLX/local LLM optional)
5. Result goes to cloud LLM along with persona prompt and user priorities
6. `privacy_level: "private"` is a kill switch that skips blocks entirely and sends only category summaries

**Key files:**
- `coach/blocks.py` — ActivityBlock, ActivityTimeline, ActivityBlockBuilder, ActivityBlockFormatter (~900 lines, the core of the pipeline)
- `coach/privacy_scrubber.py` — PrivacyScrubber with regex fallback
- `coach/digest.py` — Orchestrates the pipeline, calls the cloud LLM
- `process/spatial.py` — Maps OCR bounding boxes to visible windows (upstream of blocks)
- `storage/db.py` — `get_activity_metadata_timeline()` query

**Per-capture metadata structure** (stored in `activity_log.metadata`):
```json
{
  "windows": [
    {"app_name": "Firefox", "window_title": "Google Docs", "focused": true,
     "screen_percentage": 60.0, "ocr_text": "...", "ocr_char_count": 450},
    {"app_name": "Slack", "window_title": "#general", "focused": false, ...}
  ],
  "processing": {
    "activity_type": "active_work",
    "change_ratio": 0.15,
    "per_window_changes": [
      {"app_name": "Firefox", "window_title": "Google Docs", "change_ratio": 0.20},
      {"app_name": "Slack", "window_title": "#general", "change_ratio": 0.02}
    ]
  }
}
```

## When Making Changes
- Maintain privacy-first design - no raw data to external services
- Respect privacy levels: `private` mode must never send app names, window titles, or project context to the API
- Keep persona prompts under 600 tokens each
- Test capture daemon with short intervals (5s) during development
- Don't commit anything in `data/`, `config.yaml`, or `priorities.md`
- Follow existing code patterns and conventions

## Known Limitations
- OCR requires macOS Vision framework (13+)
- Some pyobjc dependencies may need manual installation
- API key required for digest generation (set ANTHROPIC_API_KEY)

## Dependencies
- Python 3.9.6+
- macOS 13+ (for Vision framework OCR)
- See pyproject.toml for full dependency list