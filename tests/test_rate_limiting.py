import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure ai_manager can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_manager import AIManager, RateLimitError

class TestRateLimitFix(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = AIManager()
        self.manager.provider = 'gemini-api'
        self.manager.gemini_api_key = 'fake-key'
        self.manager.gemini_model = 'gemini-pro'

        # Mock RateLimiter to avoid waiting 4s per call
        self.manager.rate_limiter.acquire = AsyncMock()

        # Mock asyncio.sleep to avoid waiting 4s/8s/16s
        self.sleep_patcher = patch('asyncio.sleep', new_callable=AsyncMock)
        self.mock_sleep = self.sleep_patcher.start()

    async def asyncTearDown(self):
        self.sleep_patcher.stop()
        await self.manager.close()

    async def test_retry_on_429_persistent_failure(self):
        """
        Test that it retries 3 times on persistent 429 and calls callback.
        """
        mock_session = AsyncMock()
        mock_session.closed = False
        self.manager.session = mock_session

        # Mock response: Always 429
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text.return_value = "Resource exhausted"

        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_session.post = MagicMock(return_value=mock_post_ctx)

        retry_callback = AsyncMock()

        response = await self.manager.generate_response("test", retry_callback=retry_callback)

        self.assertEqual(response, "", "Should return empty string after exhaustion")
        self.assertEqual(mock_session.post.call_count, 4, "Should call API 4 times (1 + 3 retries)")
        self.assertEqual(retry_callback.call_count, 3, "Callback should be called 3 times")

        # Verify sleeps: 4, 8, 16
        expected_calls = [unittest.mock.call(4.0), unittest.mock.call(8.0), unittest.mock.call(16.0)]
        # Note: There might be other sleeps from rate limiter if I didn't mock it well?
        # I mocked rate_limiter.acquire in asyncSetUp, so only generate_response sleeps should happen.
        self.mock_sleep.assert_has_calls(expected_calls)

    async def test_retry_success_after_failure(self):
        """
        Test that it retries once and succeeds.
        """
        mock_session = AsyncMock()
        mock_session.closed = False
        self.manager.session = mock_session

        # Mock response: 429 then 200
        fail_response = AsyncMock()
        fail_response.status = 429
        fail_response.text.return_value = "Exhausted"

        success_response = AsyncMock()
        success_response.status = 200
        success_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Success!"}]}}]}

        # Side effect for __aenter__
        # We need a context manager that returns different responses
        # This is tricky with MagicMock.
        # Let's mock the session.post return value (the context manager)
        # to return a context manager whose __aenter__ has side effects.

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=[fail_response, success_response])
        ctx.__aexit__ = AsyncMock(return_value=None)

        mock_session.post = MagicMock(return_value=ctx)

        retry_callback = AsyncMock()

        response = await self.manager.generate_response("test", retry_callback=retry_callback)

        self.assertEqual(response, "Success!", "Should return success response")
        self.assertEqual(mock_session.post.call_count, 2, "Should call API 2 times")
        self.assertEqual(retry_callback.call_count, 1, "Callback should be called 1 time")

        self.mock_sleep.assert_called_once_with(4.0)

if __name__ == '__main__':
    unittest.main()
