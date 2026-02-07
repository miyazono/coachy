# Coachy Development Context

## What This Project Is
Coachy is a local-first productivity monitoring and coaching system. It captures periodic screenshots, extracts activity context, and generates coaching digests using configurable AI personas.

## Key Design Constraints
1. **Privacy-first**: All capture and processing happens locally. Only aggregated summaries go to external LLMs.
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
│   │   └── window.py         # AppKit window detection
│   ├── process/              # Activity processing
│   │   ├── ocr.py           # Vision framework OCR
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
├── config.yaml              # User configuration
├── priorities.md            # User's current priorities
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

### 🔲 Phase 5: Polish and Reliability (Next)
- Retention policy cleanup
- Comprehensive error handling
- Edge case handling
- Production-ready reliability

## CLI Commands

**Core Operations:**
- `python3 -m coachy.cli start` - Start capture daemon
- `python3 -m coachy.cli stop` - Stop capture daemon
- `python3 -m coachy.cli status` - Check status & stats

**Coaching:**
- `python3 -m coachy.cli digest` - Generate coaching digest
- `python3 -m coachy.cli digest --coach huang` - Use specific coach
- `python3 -m coachy.cli digest --period week` - Weekly digest
- `python3 -m coachy.cli coaches` - List available coaches

**Configuration:**
- `python3 -m coachy.cli configure` - Edit config.yaml
- `python3 -m coachy.cli priorities` - Edit priorities.md
- `python3 -m coachy.cli categories` - Show activity categories

**Maintenance:**
- `python3 -m coachy.cli cleanup` - Clean old data
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
```

## When Making Changes
- Maintain privacy-first design - no raw data to external services
- Keep persona prompts under 600 tokens each
- Test capture daemon with short intervals (5s) during development
- Don't commit anything in `data/`
- Follow existing code patterns and conventions

## Known Limitations
- OCR requires macOS Vision framework (13+)
- Some pyobjc dependencies may need manual installation
- API key required for digest generation (set ANTHROPIC_API_KEY)

## Dependencies
- Python 3.9.6+
- macOS 13+ (for Vision framework OCR)
- See pyproject.toml for full dependency list