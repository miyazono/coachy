# Coachy - Personal Productivity Coach

Coachy is a local-first productivity monitoring and coaching system for macOS. It captures periodic screenshots, extracts activity context using native OCR, and generates coaching digests using configurable AI personas.

## Features

- **Privacy-first**: All screenshots and OCR stay local. Only aggregated summaries go to the LLM, controlled by configurable privacy levels.
- **Automatic activity tracking**: Captures screenshots every 60s, classifies your work into 8 categories.
- **Spatial window-aware OCR**: Maps recognized text to specific visible windows so the system knows what you're actively working on vs. what's in the background.
- **AI coaching digests**: Get feedback from different coaching perspectives (Andy Grove by default, or add your own).
- **Priority-driven**: Compare actual time allocation against your stated goals.

## Requirements

- **macOS 13+** (Ventura or later) — required for Vision framework OCR and Quartz screenshot capture
- **Python 3.9+**
- **Screen Recording permission** — System Settings > Privacy & Security > Screen Recording (grant to Terminal / your terminal app)
- **Anthropic API key** — for coaching digests (or use a local LLM for fully offline operation)

## Installation

1. **Clone the repository:**
```bash
git clone https://github.com/miyazono/coachy.git
cd coachy
```

2. **Install dependencies:**
```bash
pip3 install --user anthropic click pyyaml pillow openai
pip3 install --user pyobjc-framework-Quartz pyobjc-framework-AppKit pyobjc-framework-Vision
```

Or install everything from `pyproject.toml`:
```bash
pip3 install --user -e .
```

3. **Set your Anthropic API key:**
```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

4. **First-run setup** (auto-creates `config.yaml` and `priorities.md` from examples):
```bash
python3 -m coachy.cli status
```

## Usage

**Start tracking:**
```bash
python3 -m coachy.cli start
```

**Check status:**
```bash
python3 -m coachy.cli status
```

**Generate a coaching digest:**
```bash
python3 -m coachy.cli digest
python3 -m coachy.cli digest --coach grove        # Specific coach
python3 -m coachy.cli digest --period week         # Weekly digest
python3 -m coachy.cli digest --privacy detailed    # Include app names and window context
```

**Stop tracking:**
```bash
python3 -m coachy.cli stop
```

## Commands

| Command | Description |
|---------|-------------|
| `start` | Start the capture daemon |
| `stop` | Stop the capture daemon |
| `status` | Check status and basic statistics |
| `stats` | Show detailed activity breakdown |
| `digest` | Generate coaching digest (`--coach`, `--period`, `--date`, `--privacy`, `--archive`) |
| `coaches` | List available coaching personas |
| `priorities` | Edit your priorities file |
| `configure` | Edit configuration |
| `categories` | Show activity categories |
| `cleanup` | Clean old data (`--days N`) |
| `wipe --confirm` | Delete ALL captured data (screenshots, database, logs) |
| `test` | Test components (`--test-classifier`, `--test-ocr`) |

## Coaches

Run `python3 -m coachy.cli coaches` to see available coaches.

The default coach is **Andy Grove** (high output management, leverage thinking). Add custom personas by placing markdown files in `personas/` or `private-personas/` (gitignored) — see `personas/grove.md` for the format.

## Configuration

On first run, `config.yaml` is created from `config.yaml.example`. Key settings:

```yaml
capture:
  interval_seconds: 60      # Capture frequency
  monitors: "primary"       # Which display to capture
  excluded_apps:             # Apps to skip (no screenshot taken)
    - "1Password"
    - "Zoom"

storage:
  retention_days: 30         # Auto-delete data older than this

coach:
  default_persona: "grove"
  privacy_level: "private"   # "private" or "detailed"
```

## Privacy

See [PRIVACY.md](PRIVACY.md) for the full data flow.

**Key points:**
- Screenshots, OCR text, and window titles **never leave your machine**.
- The `digest` command sends only an aggregated summary to the LLM API.
- **`private` mode** (default): sends only category durations and hourly timeline — no app names, window titles, or OCR text.
- **`detailed` mode**: also includes app names, productive session context, and workspace layout patterns.
- Use `--privacy` flag to override per-invocation.
- Set `coach.llm_provider` to `"local"` or `"mlx"` for fully offline operation (zero network calls).
- All data files are stored with owner-only permissions (`0o600`).
- No telemetry, no analytics, no update checks.

## Activity Categories

Coachy automatically classifies activities using app name, window title, and OCR text:

| Category | Examples |
|----------|----------|
| `deep_work` | VS Code, PyCharm, Obsidian |
| `communication` | Slack, Mail, Messages |
| `meetings` | Zoom, Meet, Teams (detected but not captured) |
| `research` | Chrome, Safari, Firefox |
| `social_media` | Twitter/X, LinkedIn, Reddit |
| `administrative` | Calendar, Finder, task managers |
| `break` | YouTube, Spotify, Netflix |
| `unknown` | Unclassified activity |

## Architecture

- **Capture**: Screenshots via Quartz, active window via AppKit, visible window enumeration via CGWindowList
- **Processing**: OCR with Vision framework (flat text + bounding-box spatial mode), rules-based classification, per-window text mapping
- **Inference**: Screenshot diffing with per-window change detection to identify idle, reading, active work, and context switches
- **Storage**: SQLite with WAL mode, automatic retention cleanup, JSON metadata
- **Coaching**: Anthropic Claude API (or local LLM) with configurable personas and privacy levels

## Troubleshooting

**"No activity data"**: Make sure capture is running — check with `python3 -m coachy.cli status`.

**"API key not found"**: Set `export ANTHROPIC_API_KEY=your_key` in your shell profile.

**No screenshots captured**: Grant Screen Recording permission in System Settings > Privacy & Security > Screen Recording. You may need to restart your terminal after granting it.

**OCR not working**: Requires macOS 13+ (Ventura). Check with `python3 -m coachy.cli test --test-ocr`.

## Development

See [CLAUDE.md](CLAUDE.md) for detailed development documentation.

Run tests:
```bash
python3 test_basic.py                    # Core functionality
python3 test_phase2.py                   # Processing pipeline
python3 test_phase3.py                   # Digest generation
python3 test_phase4.py                   # Coach personas
python3 -m unittest test_spatial -v      # Spatial OCR (Phase 6)
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- Built with [Claude](https://anthropic.com/claude) by Anthropic
- Default coaching persona inspired by Andy Grove's *High Output Management*
- Uses macOS native frameworks (Vision, Quartz, AppKit) for privacy-preserving capture
