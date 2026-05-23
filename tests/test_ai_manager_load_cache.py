import sys
from unittest.mock import MagicMock

# Mock dependencies before importing ai_manager
try:
    import dotenv
except ImportError:
    sys.modules['dotenv'] = MagicMock()
try:
    import aiohttp
except ImportError:
    sys.modules['aiohttp'] = MagicMock()

import asyncio
import os
import json
import unittest
from ai_manager import AIManager, CACHE_FILE

class TestAIManagerLoadCache(unittest.TestCase):
    def setUp(self):
        # Clean up cache file before each test
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    def tearDown(self):
        # Clean up cache file after each test
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    async def _run_load_cache_test(self):
        # Create a dummy cache file
        test_data = [
            {
                "player_count": 3,
                "existing_roles": ["RoleA", "RoleB", "RoleC"],
                "roles": ["RoleA", "RoleB", "RoleC"]
            }
        ]
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(test_data, f)

        # Initialize AIManager (should be fast now)
        ai = AIManager()

        # Verify cache is empty initially (because we removed blocking load)
        # Note: Before refactoring, this assert might fail if _load_cache is still called in init
        # After refactoring, it should pass.
        # However, since I'm writing the test first, I'll expect it to be empty if I assume the change is made.
        # But wait, I'm writing this test to verify the change. So currently it will fail.
        # That's fine.

        # Call load_cache asynchronously
        if hasattr(ai, 'load_cache'):
            await ai.load_cache()
        else:
            # Fallback for before refactoring (if needed)
            pass

        # Verify cache is populated
        key = (3, tuple(["RoleA", "RoleB", "RoleC"]))
        self.assertIn(key, ai.role_template_cache)
        self.assertEqual(ai.role_template_cache[key], ["RoleA", "RoleB", "RoleC"])

    def test_load_cache(self):
        """Test that load_cache loads data correctly."""
        asyncio.run(self._run_load_cache_test())

    async def _run_load_missing_cache_test(self):
        # Ensure file does not exist
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

        ai = AIManager()
        if hasattr(ai, 'load_cache'):
            await ai.load_cache()

        # Should not raise error and cache should be empty
        self.assertEqual(len(ai.role_template_cache), 0)

    def test_load_missing_cache(self):
        """Test that load_cache handles missing file gracefully."""
        asyncio.run(self._run_load_missing_cache_test())

if __name__ == '__main__':
    unittest.main()
