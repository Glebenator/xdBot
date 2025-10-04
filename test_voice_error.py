#!/usr/bin/env python3
"""Test script to reproduce and diagnose the FFmpeg error."""

import asyncio
import sys
sys.path.insert(0, '.')

# Force clean import
for mod in list(sys.modules.keys()):
    if 'voice_handler' in mod or 'music' in mod:
        del sys.modules[mod]

async def test_voice_handler():
    """Test the voice handler with a simple query."""
    try:
        from utils.voice_handler import YTDLSource, FFMPEG_OPTIONS
        
        print("=" * 60)
        print("Testing Voice Handler")
        print("=" * 60)
        
        print("\n1. Checking FFMPEG_OPTIONS:")
        print(f"   Keys: {list(FFMPEG_OPTIONS.keys())}")
        print(f"   Values: {FFMPEG_OPTIONS}")
        
        print("\n2. Testing get_info() for a search query:")
        query = "rezz"
        print(f"   Query: {query}")
        
        try:
            info = await YTDLSource.get_info(query)
            print(f"   ✅ Successfully extracted info")
            print(f"   Title: {info.get('title', 'Unknown')}")
            print(f"   URL: {info.get('url', 'Unknown')[:80]}...")
            print(f"   Webpage: {info.get('webpage_url', 'Unknown')}")
            
            print("\n3. Testing create_source():")
            # This is where the error should occur if there's a problem
            source = await YTDLSource.create_source(
                info['webpage_url'],
                volume=0.5
            )
            print(f"   ✅ Successfully created audio source")
            print(f"   Source type: {type(source)}")
            print(f"   Title: {source.title}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_voice_handler())
    sys.exit(0 if result else 1)
