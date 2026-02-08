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
│       ├── digest.py        # Digest generation
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
- `python3 -m coachy.cli coaches` - List available coaches

**Configuration:**
- `python3 -m coachy.cli configure` - Edit config.yaml
- `python3 -m coachy.cli priorities` - Edit priorities.md
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