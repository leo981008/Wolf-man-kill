
import sys
import unittest
from unittest.mock import MagicMock, patch

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
import tempfile
import time

# Now import AIManager
from ai_manager import AIManager, CACHE_FILE

class TestAIManagerSaveCache(unittest.TestCase):
    def setUp(self):
        # Clean up cache file before each test
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    def tearDown(self):
        # Clean up cache file after each test
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)

    async def _run_save_cache_test(self):
        ai = AIManager()
        # Mock role_template_cache
        test_roles = ["RoleA", "RoleB", "RoleC"]
        test_key = (3, tuple(["RoleA", "RoleB", "RoleC"]))
        ai.role_template_cache[test_key] = test_roles

        # Call save_cache (expecting it to be async)
        await ai._save_cache()

        # Verify file exists
        self.assertTrue(os.path.exists(CACHE_FILE), "Cache file should exist")

        # Verify content
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.assertEqual(len(data), 1)
            entry = data[0]
            self.assertEqual(entry["player_count"], 3)
            self.assertEqual(entry["existing_roles"], ["RoleA", "RoleB", "RoleC"])
            self.assertEqual(entry["roles"], test_roles)

    def test_save_cache(self):
        """Test that _save_cache saves data correctly."""
        asyncio.run(self._run_save_cache_test())

if __name__ == '__main__':
    unittest.main()
