# Coachy - Personal Productivity Coach

Coachy is a local-first productivity monitoring and coaching system that helps you understand how you spend your time and provides personalized coaching feedback from different perspectives.

## Features

- 🔒 **Privacy-first**: All screenshots and data stay local - only aggregated summaries go to AI
- 📸 **Automatic activity tracking**: Captures screenshots and categorizes your work
- 🤖 **Multiple AI coaches**: Get feedback from different coaching perspectives
- 📊 **Rich analytics**: Understand your time allocation vs. priorities
- 🎯 **Priority-driven**: Compare actual time spent against your stated goals

## Quick Start

### Prerequisites

- macOS 13+ (for screenshot and OCR features)
- Python 3.9+
- Anthropic API key for coaching digests

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/miyazono/coachy.git
cd coachy
```

2. **Install dependencies:**
```bash
pip3 install --user anthropic click pyyaml pillow
# macOS frameworks for screenshots (may require additional setup)
pip3 install --user pyobjc-framework-Quartz pyobjc-framework-AppKit pyobjc-framework-Vision
```

3. **Set your Anthropic API key:**
```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

### Usage

**Start tracking your activity:**
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
```

**Stop tracking:**
```bash
python3 -m coachy.cli stop
```

## Daily Workflow

1. **Morning:** Start Coachy when you begin work
   ```bash
   python3 -m coachy.cli start
   ```

2. **During the day:** Work normally - Coachy captures activity every 60 seconds

3. **End of day:** Get coaching feedback
   ```bash
   python3 -m coachy.cli digest
   ```

4. **Try different coaches** for varied perspectives:
   ```bash
   python3 -m coachy.cli coaches              # List available coaches
   python3 -m coachy.cli digest --coach grove  # Use a specific coach
   ```

## Available Coaches

Run `python3 -m coachy.cli coaches` to see all available coaches.

The default coach is **Andy Grove** (high output management, leverage thinking). You can add custom personas by placing markdown files in `personas/` or `private-personas/` (gitignored) — see `personas/grove.md` for the format.

## Commands

### Core Operations
- `start` - Start activity capture
- `stop` - Stop capture
- `status` - Check status and statistics
- `stats` - Show detailed activity breakdown

### Coaching
- `digest` - Generate coaching digest (default: Andy Grove, daily)
- `digest --coach <name>` - Use specific coach
- `digest --period week` - Weekly digest
- `coaches` - List available coaching personas

### Configuration
- `priorities` - Edit your priorities file
- `configure` - Edit configuration
- `categories` - Show activity categories

### Maintenance
- `cleanup` - Clean old data
- `test --test-classifier` - Test activity classification
- `test --test-ocr` - Test OCR functionality

## Configuration

Edit `config.yaml` to customize:

```yaml
capture:
  interval_seconds: 60  # How often to capture
  monitors: "primary"   # Which monitors to capture
  
storage:
  retention_days: 30    # How long to keep screenshots
  
coach:
  default_persona: "grove"  # Default coach
```

## Privacy & Security

- **All data stays local** - screenshots never leave your machine
- **Only summaries sent to AI** - like "2 hours in VS Code, 1 hour email"
- **Automatic exclusions** - password managers, video calls skipped
- **30-day retention** - old screenshots auto-deleted

## Activity Categories

Coachy automatically categorizes your activities:

- **deep_work**: Coding, writing, research, analysis
- **communication**: Email, Slack, messaging
- **meetings**: Video calls (detected but not captured)
- **research**: Reading, learning, browsing
- **social_media**: Twitter, LinkedIn, Reddit
- **administrative**: Calendar, task management
- **break**: Entertainment, relaxation
- **unknown**: Uncategorized activity

## Troubleshooting

**"No activity data"**: Make sure capture is running with `coachy status`

**"API key not found"**: Set `export ANTHROPIC_API_KEY=your_key`

**macOS permissions**: Grant screen recording permission in System Preferences → Security & Privacy

**OCR not working**: Requires macOS 13+ with Vision framework

## Architecture

Coachy uses a modular architecture:

- **Capture system**: Screenshots via Quartz, window info via AppKit
- **Processing pipeline**: OCR with Vision framework, rules-based classification
- **Storage**: SQLite database with retention policies
- **Coaching system**: Anthropic Claude API with multiple personas

## Development

See [CLAUDE.md](CLAUDE.md) for development documentation.

Run tests:
```bash
python3 test_basic.py    # Core functionality
python3 test_phase2.py   # Processing pipeline
python3 test_phase3.py   # Digest generation
python3 test_phase4.py   # Coach personas
```

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## Acknowledgments

- Inspired by productivity research from Andy Grove, Cal Newport, and others
- Built with Claude by Anthropic
- Uses macOS native frameworks for privacy-preserving capture