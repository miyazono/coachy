#!/usr/bin/env python3
"""Basic test of Coachy functionality."""
import sys
import pathlib

# Add current directory to path so we can import coachy
sys.path.insert(0, str(pathlib.Path(__file__).parent))

def test_config():
    """Test configuration loading."""
    print("Testing configuration loading...")
    try:
        from coachy.config import get_config
        config = get_config()
        print(f"✓ Config loaded: capture_interval={config.capture_interval}s")
        print(f"✓ Database path: {config.db_path}")
        print(f"✓ Screenshots path: {config.screenshots_path}")
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False

def test_database():
    """Test database initialization."""
    print("\nTesting database initialization...")
    try:
        from coachy.storage.db import get_database
        from coachy.storage.models import ActivityEntry
        
        # Initialize database
        db = get_database("data/test.db")
        
        # Test basic database operations
        stats = db.get_database_stats()
        print(f"✓ Database initialized with {stats['activity_entries']} entries")
        
        # Test creating an activity entry
        activity = ActivityEntry.create_now(
            app_name="TestApp",
            window_title="Test Window",
            category="test"
        )
        
        activity_id = db.insert_activity(activity)
        print(f"✓ Test activity created with ID: {activity_id}")
        
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_cli_import():
    """Test CLI module import."""
    print("\nTesting CLI import...")
    try:
        from coachy.cli import cli
        print("✓ CLI module imported successfully")
        return True
    except Exception as e:
        print(f"✗ CLI import failed: {e}")
        return False

def test_capture_import():
    """Test capture module import (without macOS dependencies)."""
    print("\nTesting capture modules...")
    try:
        from coachy.capture import daemon
        print("✓ Capture daemon module imported")
        
        # Test daemon status function (doesn't require macOS frameworks)
        status = daemon.get_daemon_status()
        print(f"✓ Daemon status check: running={status['running']}")
        
        return True
    except Exception as e:
        print(f"✗ Capture test failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Coachy Basic Functionality Test ===")
    
    tests = [
        test_config,
        test_database, 
        test_cli_import,
        test_capture_import
    ]
    
    passed = 0
    for test_func in tests:
        if test_func():
            passed += 1
    
    print(f"\n=== Results: {passed}/{len(tests)} tests passed ===")
    
    if passed == len(tests):
        print("🎉 All basic tests passed! Phase 1 foundation is working.")
        print("\nNext steps:")
        print("1. Install macOS dependencies for screenshot capture")
        print("2. Test with: python3 test_basic.py")
        print("3. Try: python3 -m coachy.cli --help")
    else:
        print("❌ Some tests failed. Check the errors above.")
        sys.exit(1)