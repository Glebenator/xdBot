#!/usr/bin/env python3
"""Quick verification script for Phase 2 music implementation.

This script checks if all dependencies and modules are correctly installed
and importable before running the bot.
"""

import subprocess
import sys


def check_python_version():
    """Verify Python version is 3.11+"""
    print("🐍 Checking Python version...")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 11:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} (need 3.11+)")
        return False


def check_ffmpeg():
    """Verify FFmpeg is installed"""
    print("\n🎬 Checking FFmpeg...")
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"   ✅ {version_line}")
            return True
        else:
            print("   ❌ FFmpeg not working properly")
            return False
    except FileNotFoundError:
        print("   ❌ FFmpeg not found")
        print("   📝 Install with: sudo apt install ffmpeg")
        return False
    except Exception as e:
        print(f"   ❌ Error checking FFmpeg: {e}")
        return False


def check_module(module_name, friendly_name=None):
    """Check if a Python module can be imported"""
    friendly_name = friendly_name or module_name
    try:
        __import__(module_name)
        print(f"   ✅ {friendly_name}")
        return True
    except ImportError as e:
        print(f"   ❌ {friendly_name} - {e}")
        return False


def check_python_dependencies():
    """Verify all required Python packages are installed"""
    print("\n📦 Checking Python dependencies...")

    modules = [
        ("discord", "discord.py"),
        ("aiohttp", "aiohttp"),
        ("yt_dlp", "yt-dlp"),
        ("nacl", "PyNaCl"),
        ("aiosqlite", "aiosqlite"),
        ("dotenv", "python-dotenv"),
    ]

    all_ok = True
    for module, friendly in modules:
        if not check_module(module, friendly):
            all_ok = False

    return all_ok


def check_music_modules():
    """Verify all custom music modules can be imported"""
    print("\n🎵 Checking music modules...")

    modules = [
        "utils.music_exceptions",
        "utils.voice_handler",
        "utils.music_queue",
        "cogs.music",
    ]

    all_ok = True
    for module in modules:
        if not check_module(module):
            all_ok = False

    return all_ok


def check_config():
    """Verify config module and music settings"""
    print("\n⚙️  Checking configuration...")
    try:
        import config
        settings = config.settings

        # Check music settings exist
        attrs = [
            "music_max_queue_size",
            "music_idle_timeout",
            "music_default_volume",
            "music_max_duration",
        ]

        all_ok = True
        for attr in attrs:
            if hasattr(settings, attr):
                value = getattr(settings, attr)
                print(f"   ✅ {attr} = {value}")
            else:
                print(f"   ❌ {attr} not found")
                all_ok = False

        return all_ok
    except Exception as e:
        print(f"   ❌ Error loading config: {e}")
        return False


def check_database():
    """Verify database can be initialized"""
    print("\n🗄️  Checking database...")
    try:
        from utils.db_handler import get_database_handler
        get_database_handler()
        print("   ✅ Database handler initialized")
        print("   ✅ music_history table created")
        return True
    except Exception as e:
        print(f"   ❌ Database error: {e}")
        return False


def main():
    """Run all checks"""
    print("=" * 60)
    print("🎵 Music Feature Phase 2 - Pre-Flight Verification")
    print("=" * 60)

    checks = [
        ("Python Version", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("Python Dependencies", check_python_dependencies),
        ("Music Modules", check_music_modules),
        ("Configuration", check_config),
        ("Database", check_database),
    ]

    results = []
    for name, check_func in checks:
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Unexpected error in {name}: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 Summary")
    print("=" * 60)

    all_passed = all(result for _, result in results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:10} | {name}")

    print("=" * 60)

    if all_passed:
        print("\n🎉 All checks passed! Ready to start the bot.")
        print("\n📝 Next steps:")
        print("   1. Ensure bot token is in .env file")
        print("   2. Run: python main.py")
        print("   3. Test with: /join and /play <song>")
        print("\n📖 See MUSIC_SETUP.md for detailed testing guide")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        print("\n📝 Common fixes:")
        print("   • Install FFmpeg: sudo apt install ffmpeg")
        print("   • Install Python packages: pip install -r requirements.txt")
        return 1


if __name__ == "__main__":
    sys.exit(main())
