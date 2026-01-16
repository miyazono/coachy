"""Command-line interface for Coachy."""
import pathlib
import sys
from datetime import datetime

import click

from . import __version__
from .capture import daemon
from .config import get_config
from .storage.db import get_database
from .process.pipeline import create_processor
from .storage.models import CATEGORIES


@click.group()
@click.version_option(version=__version__)
def cli():
    """Coachy: Personal Productivity Coach
    
    Captures periodic screenshots and provides coaching insights.
    """
    pass


@cli.command()
def start():
    """Start the capture daemon."""
    try:
        daemon.start_daemon()
        click.echo("✓ Coachy capture started.")
    except RuntimeError as e:
        click.echo(f"✗ Failed to start: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
def stop():
    """Stop the capture daemon."""
    try:
        daemon.stop_daemon()
        click.echo("✓ Coachy capture stopped.")
    except RuntimeError as e:
        click.echo(f"✗ Failed to stop: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


@cli.command()
def status():
    """Show capture status and statistics."""
    try:
        config = get_config()
        
        # Get daemon status
        daemon_status = daemon.get_daemon_status()
        
        # Basic status
        if daemon_status["running"]:
            click.echo(f"🟢 Coachy is running (PID: {daemon_status['pid']})")
        else:
            click.echo("🔴 Coachy is not running")
            if daemon_status.get("stale_pid_removed"):
                click.echo("  (Removed stale PID file)")
        
        # Configuration summary
        click.echo(f"📁 Database: {config.db_path}")
        click.echo(f"📸 Screenshots: {config.screenshots_path}")
        click.echo(f"⏱️  Capture interval: {config.capture_interval}s")
        click.echo(f"🖥️  Monitor mode: {config.capture_monitors}")
        
        # Database statistics
        try:
            db = get_database(config.db_path)
            stats = db.get_database_stats()
            
            click.echo("\n📊 Database Statistics:")
            click.echo(f"  Activity entries: {stats['activity_entries']:,}")
            click.echo(f"  Digest entries: {stats['digest_entries']:,}")
            click.echo(f"  Database size: {stats['file_size_bytes'] / 1024 / 1024:.1f} MB")
            
            if stats['earliest_activity'] and stats['latest_activity']:
                earliest = datetime.fromtimestamp(stats['earliest_activity'])
                latest = datetime.fromtimestamp(stats['latest_activity'])
                click.echo(f"  Date range: {earliest.strftime('%Y-%m-%d')} to {latest.strftime('%Y-%m-%d')}")
                
        except Exception as e:
            click.echo(f"  Database error: {e}")
        
        # Processing configuration
        try:
            processor = create_processor()
            proc_stats = processor.get_processing_stats()
            
            click.echo("\n🔧 Processing Configuration:")
            click.echo(f"  OCR enabled: {proc_stats['ocr_enabled']}")
            click.echo(f"  Classifier backend: {proc_stats['classifier_backend']}")
            click.echo(f"  Available categories: {len(proc_stats['available_categories'])}")
            
        except Exception as e:
            click.echo(f"  Processing config error: {e}")
        
        # Storage usage
        try:
            screenshots_path = pathlib.Path(config.screenshots_path)
            if screenshots_path.exists():
                screenshot_files = list(screenshots_path.glob("*.jpg"))
                total_size = sum(f.stat().st_size for f in screenshot_files)
                
                click.echo("\n📷 Screenshot Storage:")
                click.echo(f"  Files: {len(screenshot_files):,}")
                click.echo(f"  Total size: {total_size / 1024 / 1024:.1f} MB")
            else:
                click.echo("\n📷 Screenshot Storage: Directory not found")
        except Exception as e:
            click.echo(f"\n📷 Screenshot Storage: Error - {e}")
        
    except Exception as e:
        click.echo(f"✗ Error getting status: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--period', type=click.Choice(['day', 'week']), default='day', help='Period for digest (day or week)')
@click.option('--coach', 'persona', default=None, help='Coach persona to use (default: grove)')
@click.option('--date', default=None, help='Specific date (YYYY-MM-DD) or "yesterday"')
@click.option('--archive', is_flag=True, help='Preserve screenshots after digest (default: delete them)')
def digest(period, persona, date, archive):
    """Generate a coaching digest.

    By default, screenshots are deleted after the digest is generated to save space.
    Use --archive to preserve them.
    """
    try:
        # Import here to avoid import issues if dependencies not available
        from .coach.digest import DigestGenerator

        config = get_config()

        # Use default persona if not specified
        if persona is None:
            persona = config.get('coach.default_persona', 'grove')

        click.echo(f"🤖 Generating {period} digest with {persona} coach...")

        # Create generator to access time range
        generator = DigestGenerator()

        # Get the time range for this digest
        start_timestamp, end_timestamp = generator._get_time_range(period, date)

        # Generate digest
        digest_content = generator.generate_digest(
            period=period,
            persona=persona,
            date=date
        )

        click.echo("\n" + "="*60)
        click.echo(digest_content)
        click.echo("="*60)

        # Delete screenshots unless --archive flag is set
        if not archive:
            deleted_count = _cleanup_screenshots_for_period(
                config.screenshots_path,
                start_timestamp,
                end_timestamp
            )
            if deleted_count > 0:
                click.echo(f"\n🗑️  Cleaned up {deleted_count} screenshots (use --archive to preserve)")
        else:
            click.echo(f"\n📦 Screenshots archived (not deleted)")

    except ImportError as e:
        click.echo(f"✗ Missing dependencies for digest generation: {e}", err=True)
        click.echo("   Install with: pip install anthropic", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Digest generation failed: {e}", err=True)
        sys.exit(1)


def _cleanup_screenshots_for_period(screenshots_path: str, start_ts: int, end_ts: int) -> int:
    """Delete screenshots within the specified time period.

    Args:
        screenshots_path: Path to screenshots directory
        start_ts: Start timestamp (Unix)
        end_ts: End timestamp (Unix)

    Returns:
        Number of screenshots deleted
    """
    screenshots_dir = pathlib.Path(screenshots_path)
    if not screenshots_dir.exists():
        return 0

    deleted_count = 0

    for screenshot_file in screenshots_dir.glob("screenshot_*.jpg"):
        try:
            # Extract timestamp from filename (screenshot_1234567890123.jpg)
            filename = screenshot_file.stem
            ts_str = filename.replace("screenshot_", "")
            file_ts = int(ts_str) // 1000  # Convert ms to seconds

            # Check if within time range
            if start_ts <= file_ts <= end_ts:
                screenshot_file.unlink()
                deleted_count += 1

        except (ValueError, OSError) as e:
            # Skip files that don't match expected pattern or can't be deleted
            continue

    return deleted_count


@cli.command()
def configure():
    """Edit configuration file."""
    config_path = pathlib.Path("config.yaml")
    
    if not config_path.exists():
        click.echo(f"Configuration file not found: {config_path}")
        return
    
    click.edit(filename=str(config_path))
    click.echo("Configuration edited. Restart daemon for changes to take effect.")


@cli.command()
def priorities():
    """Edit priorities file."""
    priorities_path = pathlib.Path("priorities.md")
    
    if not priorities_path.exists():
        # Create a default priorities file
        default_content = """# Coachy Priorities
# Update this file daily or weekly. Your coach compares actual activity against these.

## This Week's Priorities
1. [Add your weekly priorities here]
2. [Another priority]

## Today's Focus
- [Add today's specific focus areas]

## Standing Rules
- [Add your standing productivity rules]
"""
        priorities_path.write_text(default_content)
        click.echo(f"Created default priorities file: {priorities_path}")
    
    click.edit(filename=str(priorities_path))
    click.echo("Priorities updated.")


@cli.command()
@click.option('--days', default=None, type=int, help='Override retention days from config')
def cleanup(days):
    """Run storage cleanup."""
    try:
        config = get_config()
        db = get_database(config.db_path)
        
        # Determine retention period
        retention_days = days if days is not None else config.retention_days
        cutoff_timestamp = int((datetime.now().timestamp()) - (retention_days * 24 * 60 * 60))
        
        # Clean up database
        deleted_entries = db.cleanup_old_activities(cutoff_timestamp)
        
        # Clean up screenshot files
        screenshots_path = pathlib.Path(config.screenshots_path)
        deleted_files = 0
        deleted_size = 0
        
        if screenshots_path.exists():
            for screenshot_file in screenshots_path.glob("*.jpg"):
                try:
                    # Extract timestamp from filename (screenshot_TIMESTAMP.jpg)
                    filename = screenshot_file.stem
                    if filename.startswith("screenshot_"):
                        timestamp_str = filename.replace("screenshot_", "")
                        timestamp = int(timestamp_str) / 1000  # Convert from milliseconds
                        
                        if timestamp < cutoff_timestamp:
                            file_size = screenshot_file.stat().st_size
                            screenshot_file.unlink()
                            deleted_files += 1
                            deleted_size += file_size
                except (ValueError, OSError) as e:
                    click.echo(f"Warning: Could not process {screenshot_file}: {e}")
        
        click.echo(f"✓ Cleanup completed (retention: {retention_days} days)")
        click.echo(f"  Database entries deleted: {deleted_entries}")
        click.echo(f"  Screenshot files deleted: {deleted_files}")
        click.echo(f"  Space freed: {deleted_size / 1024 / 1024:.1f} MB")
        
    except Exception as e:
        click.echo(f"✗ Cleanup failed: {e}", err=True)
        sys.exit(1)


@cli.command()
def categories():
    """Show all available activity categories."""
    try:
        click.echo("📁 Activity Categories\n")
        
        for category, info in CATEGORIES.items():
            description = info.get('description', 'No description')
            signals = info.get('signals', [])
            
            click.echo(f"🔹 {category}")
            click.echo(f"   {description}")
            if signals:
                click.echo(f"   Signals: {', '.join(signals[:5])}")
                if len(signals) > 5:
                    click.echo(f"   ... and {len(signals) - 5} more")
            click.echo()
            
    except Exception as e:
        click.echo(f"✗ Error showing categories: {e}", err=True)
        sys.exit(1)


@cli.command()
def coaches():
    """Show all available coaching personas."""
    try:
        from .coach.personas import get_persona_manager
        
        manager = get_persona_manager()
        personas = manager.get_all_personas()
        
        if not personas:
            click.echo("No coaching personas found.")
            return
        
        click.echo("🤖 Available Coaching Personas\n")
        
        for name, persona in personas.items():
            summary = persona.get_summary()
            content_length = len(persona.content)
            
            click.echo(f"👨‍💼 {name}")
            click.echo(f"   {summary}")
            click.echo(f"   Content: {content_length} characters")
            click.echo()
        
        click.echo(f"💡 Use with: coachy digest --coach <name>")
        
    except Exception as e:
        click.echo(f"✗ Error showing coaches: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--test-ocr', is_flag=True, help='Test OCR functionality')
@click.option('--test-classifier', is_flag=True, help='Test activity classifier')
def test(test_ocr, test_classifier):
    """Test processing components."""
    try:
        if test_ocr:
            click.echo("🔍 Testing OCR functionality...")
            from .process.ocr import get_ocr_capabilities, test_ocr_functionality
            
            capabilities = get_ocr_capabilities()
            working = test_ocr_functionality()
            
            click.echo(f"Vision framework available: {capabilities['vision_available']}")
            click.echo(f"OCR working: {working}")
            
            if capabilities.get('error'):
                click.echo(f"Error: {capabilities['error']}")
        
        if test_classifier:
            click.echo("\n🏷️  Testing activity classifier...")
            from .process.classifier import ActivityClassifier
            
            test_cases = [
                ("VS Code", "main.py - myproject", "deep_work"),
                ("Chrome", "GitHub - microsoft/vscode", "research"),
                ("Slack", "general | MyCompany", "communication"),
                ("Zoom", "Meeting with John", "meetings"),
                ("Chrome", "Twitter", "social_media"),
            ]
            
            classifier = ActivityClassifier("rules")
            
            for app, window, expected in test_cases:
                result = classifier.classify(app, window, None)
                status = "✓" if result == expected else "✗"
                click.echo(f"  {status} {app:10} → {result:12} (expected: {expected})")
        
        if not test_ocr and not test_classifier:
            click.echo("Use --test-ocr or --test-classifier to run specific tests")
            
    except Exception as e:
        click.echo(f"✗ Test failed: {e}", err=True)
        sys.exit(1)


@cli.command()
def stats():
    """Show detailed activity statistics."""
    try:
        config = get_config()
        db = get_database(config.db_path)
        
        # Get recent activity (last 24 hours)
        now = int(datetime.now().timestamp())
        day_ago = now - (24 * 60 * 60)
        
        summary = db.get_activity_summary(day_ago, now)
        
        click.echo("📊 Activity Statistics (Last 24 Hours)\n")
        
        # Total time
        total_minutes = summary['total_tracked_minutes']
        hours = total_minutes // 60
        minutes = total_minutes % 60
        click.echo(f"⏱️  Total tracked time: {hours}h {minutes}m")
        
        # By category with descriptions
        if summary['by_category']:
            click.echo("\n📂 By Category:")
            # Sort by time spent descending
            sorted_categories = sorted(
                summary['by_category'].items(), 
                key=lambda x: x[1]['minutes'], 
                reverse=True
            )
            for category, data in sorted_categories:
                mins = data['minutes']
                pct = data['percentage']
                description = CATEGORIES.get(category, {}).get('description', 'Unknown category')
                click.echo(f"  {category:15} {mins:3}m ({pct:4.1f}%) - {description}")
        
        # By app
        if summary['by_app']:
            click.echo("\n💻 Top Applications:")
            sorted_apps = sorted(
                summary['by_app'].items(),
                key=lambda x: x[1]['minutes'],
                reverse=True
            )
            for app_name, data in sorted_apps[:10]:
                mins = data['minutes']
                category = data['category']
                click.echo(f"  {app_name:20} {mins:3}m ({category})")
        
        if total_minutes == 0:
            click.echo("\nNo activity data found for the last 24 hours.")
            click.echo("Make sure the capture daemon is running: coachy start")
        
    except Exception as e:
        click.echo(f"✗ Error getting statistics: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()