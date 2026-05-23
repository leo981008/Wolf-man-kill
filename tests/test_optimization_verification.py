import sys
from unittest.mock import MagicMock, AsyncMock

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
import unittest
from ai_manager import AIManager

class TestAIManagerOptimization(unittest.IsolatedAsyncioTestCase):
    async def test_generate_role_template_issuperset(self):
        ai = AIManager()
        # Mock generate_response to return a valid JSON array
        ai.generate_response = AsyncMock(return_value='["狼人", "預言家", "平民"]')

        # This will trigger the code path with issuperset
        existing_roles = ["狼人", "預言家", "平民"]
        roles = await ai.generate_role_template(3, existing_roles)

        self.assertEqual(roles, ["狼人", "預言家", "平民"])

        # Cache key uses sorted tuple of existing_roles
        cache_key = (3, tuple(sorted(existing_roles)))
        self.assertIn(cache_key, ai.role_template_cache)

    async def test_generate_role_template_invalid_roles(self):
        ai = AIManager()
        # Mock generate_response to return roles not in existing_roles
        ai.generate_response = AsyncMock(return_value='["狼人", "預言家", "隱身狼"]')

        roles = await ai.generate_role_template(3, ["狼人", "預言家", "平民"])

        # Should return empty list because "隱身狼" is not in existing_roles
        self.assertEqual(roles, [])

if __name__ == '__main__':
    unittest.main()
