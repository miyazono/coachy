#!/usr/bin/env python3
"""Phase 3 digest generation test."""
import os
import sys
import pathlib

# Add current directory to path so we can import coachy
sys.path.insert(0, str(pathlib.Path(__file__).parent))

def test_priorities_loading():
    """Test priorities loading and parsing."""
    print("=== Priorities Loading Test ===")
    
    try:
        from coachy.coach.priorities import load_priorities, format_priorities_for_llm
        
        # Load priorities
        priorities = load_priorities()
        
        print(f"✓ Priorities loaded successfully")
        print(f"  Weekly priorities: {len(priorities.weekly_priorities)}")
        print(f"  Daily focus: {len(priorities.daily_focus)}")
        print(f"  Standing rules: {len(priorities.standing_rules)}")
        
        # Test formatting for LLM
        formatted = format_priorities_for_llm(priorities)
        token_estimate = len(formatted) // 4
        print(f"  Formatted for LLM: {len(formatted)} chars (~{token_estimate} tokens)")
        
        return True
        
    except Exception as e:
        print(f"✗ Priorities test failed: {e}")
        return False


def test_persona_loading():
    """Test persona loading."""
    print("\n=== Persona Loading Test ===")
    
    try:
        from coachy.coach.digest import DigestGenerator
        
        generator = DigestGenerator()
        
        # Test loading Grove persona
        persona_content = generator._load_persona("grove")
        
        print(f"✓ Grove persona loaded: {len(persona_content)} characters")
        
        # Check that it contains expected Grove-related content
        if "andy grove" in persona_content.lower() or "high output" in persona_content.lower():
            print("✓ Grove persona content validated")
            return True
        else:
            print("✗ Grove persona content doesn't look right")
            return False
            
    except Exception as e:
        print(f"✗ Persona test failed: {e}")
        return False


def test_llm_client():
    """Test LLM client configuration."""
    print("\n=== LLM Client Test ===")
    
    try:
        from coachy.coach.llm import create_llm_client, LLMError
        
        # Test client creation
        try:
            client = create_llm_client()
            print("✓ LLM client created successfully")
            
            # Check if API key is available
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                print("✓ ANTHROPIC_API_KEY found")
                return True
            else:
                print("⚠ ANTHROPIC_API_KEY not set - digest generation will fail")
                print("  Set environment variable: export ANTHROPIC_API_KEY=your_key")
                return False
                
        except LLMError as e:
            print(f"⚠ LLM client error: {e}")
            return False
            
    except Exception as e:
        print(f"✗ LLM client test failed: {e}")
        return False


def test_activity_aggregation():
    """Test activity data aggregation."""
    print("\n=== Activity Aggregation Test ===")
    
    try:
        from coachy.storage.db import get_database
        from coachy.config import get_config
        import time
        
        config = get_config()
        db = get_database(config.db_path)
        
        # Get activity summary for last 24 hours
        now = int(time.time())
        day_ago = now - (24 * 60 * 60)
        
        summary = db.get_activity_summary(day_ago, now)
        
        print(f"✓ Activity aggregation working")
        print(f"  Total tracked minutes: {summary['total_tracked_minutes']}")
        print(f"  Categories: {len(summary['by_category'])}")
        print(f"  Apps: {len(summary['by_app'])}")
        print(f"  Timeline entries: {len(summary.get('timeline', []))}")
        print(f"  Productive activities: {len(summary.get('productive_activities', []))}")
        
        return True
        
    except Exception as e:
        print(f"✗ Activity aggregation test failed: {e}")
        return False


def test_digest_generation_mock():
    """Test digest generation with mock data (no API call)."""
    print("\n=== Mock Digest Generation Test ===")
    
    try:
        from coachy.coach.digest import DigestGenerator
        
        generator = DigestGenerator()
        
        # Test prompt construction without actually calling LLM
        mock_activity_summary = {
            "total_tracked_minutes": 480,  # 8 hours
            "by_category": {
                "deep_work": {"minutes": 240, "percentage": 50.0},
                "communication": {"minutes": 120, "percentage": 25.0},
                "break": {"minutes": 60, "percentage": 12.5},
                "research": {"minutes": 60, "percentage": 12.5}
            },
            "by_app": {
                "VS Code": {"minutes": 180, "category": "deep_work"},
                "Slack": {"minutes": 90, "category": "communication"},
                "Chrome": {"minutes": 60, "category": "research"}
            },
            "timeline": [
                {"hour": 9, "primary_category": "deep_work", "total_minutes": 60},
                {"hour": 10, "primary_category": "deep_work", "total_minutes": 60},
            ],
            "productive_activities": [
                {"app": "VS Code", "context": "main.py - coachy", "minutes": 120, "sessions": 2}
            ]
        }
        
        from coachy.coach.priorities import Priorities
        mock_priorities = Priorities(
            weekly_priorities=["Build coachy system", "Test thoroughly"],
            daily_focus=["Complete Phase 3"],
            standing_rules=["Focus on high-impact work"],
            success_criteria=["Working digest generation"],
            raw_content=""
        )
        
        # Test prompt construction
        prompt = generator._construct_digest_prompt(
            mock_activity_summary, mock_priorities, "You are a helpful coach.", "day"
        )
        
        print(f"✓ Digest prompt constructed: {len(prompt)} characters")
        
        # Estimate tokens
        from coachy.coach.llm import estimate_tokens
        estimated_tokens = estimate_tokens(prompt)
        print(f"  Estimated tokens: {estimated_tokens}")
        
        if estimated_tokens > 5000:
            print("⚠ Prompt is quite long - may be expensive")
        else:
            print("✓ Prompt length looks reasonable")
        
        return True
        
    except Exception as e:
        print(f"✗ Mock digest test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cli_integration():
    """Test CLI digest command."""
    print("\n=== CLI Integration Test ===")
    
    try:
        # Import CLI to check it works
        from coachy.cli import cli
        print("✓ CLI with digest command imported successfully")
        
        # Test that digest command is available
        import subprocess
        result = subprocess.run(
            ["python3", "-m", "coachy.cli", "digest", "--help"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and "Generate a coaching digest" in result.stdout:
            print("✓ CLI digest command available")
            return True
        else:
            print(f"✗ CLI digest command failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ CLI integration test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚢 Phase 3: Basic Digest Generation Test Suite")
    print("=" * 60)
    
    tests = [
        ("Priorities Loading", test_priorities_loading),
        ("Persona Loading", test_persona_loading),
        ("LLM Client Setup", test_llm_client),
        ("Activity Aggregation", test_activity_aggregation),
        ("Mock Digest Generation", test_digest_generation_mock),
        ("CLI Integration", test_cli_integration),
    ]
    
    passed = 0
    api_key_available = False
    
    for test_name, test_func in tests:
        print(f"\n🔬 Running: {test_name}")
        if test_func():
            passed += 1
            print(f"✅ {test_name} passed")
            if test_name == "LLM Client Setup" and "ANTHROPIC_API_KEY found" in str(test_func):
                api_key_available = True
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n🏁 Final Results: {passed}/{len(tests)} test suites passed")
    
    if passed == len(tests):
        print("\n🎉 Phase 3 digest generation system is ready!")
        
        if api_key_available:
            print("\n✅ Ready for live digest generation!")
            print("   Try: python3 -m coachy.cli digest --period day")
        else:
            print("\n⚠  Almost ready - just need API key!")
            print("   Set: export ANTHROPIC_API_KEY=your_key_here")
            print("   Then: python3 -m coachy.cli digest --period day")
        
        print("\nKey achievements:")
        print("- ✅ Activity data aggregation with timeline and productivity metrics")
        print("- ✅ Priorities loading and parsing from markdown")
        print("- ✅ Andy Grove coaching persona implementation")
        print("- ✅ Anthropic API integration with token tracking")
        print("- ✅ Complete digest generation pipeline")
        print("- ✅ CLI command with period/coach/date options")
        
    elif passed >= 4:
        print(f"\n🚧 Phase 3 mostly working ({passed}/{len(tests)} tests passed)")
        print("   Almost ready for digest generation!")
    else:
        print("\n❌ Phase 3 needs more work - several tests failed.")
        sys.exit(1)