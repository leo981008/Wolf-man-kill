import asyncio
import time
import unittest
import os
import sys

# Ensure ai_manager can be imported
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ai_manager import RateLimiter

class TestRateLimiterLogic(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limiting_timing(self):
        """
        Verify that RateLimiter properly spaces out requests.
        """
        # Rate: 5 tokens per second => 0.2s per token
        rate = 5.0
        capacity = 1.0
        limiter = RateLimiter(rate=rate, capacity=capacity)

        start_time = time.monotonic()

        # Acquire 1st token (should be immediate, initial capacity=1)
        await limiter.acquire()
        t1 = time.monotonic()
        self.assertLess(t1 - start_time, 0.05, "First token should be immediate")

        # Acquire 2nd token (should wait ~0.2s)
        await limiter.acquire()
        t2 = time.monotonic()
        # Since we consumed the initial token instantly, the bucket is empty (0).
        # We need 1 token. Refill rate is 5/s. Time to refill 1 = 1/5 = 0.2s.
        # So we expect ~0.2s elapsed from start.
        elapsed_2 = t2 - start_time
        self.assertGreater(elapsed_2, 0.15, "Second token should wait ~0.2s")
        self.assertLess(elapsed_2, 0.25 + 0.05) # Allow some overhead

        # Acquire 3rd token (should wait another ~0.2s)
        await limiter.acquire()
        t3 = time.monotonic()
        elapsed_3 = t3 - start_time
        self.assertGreater(elapsed_3, 0.35, "Third token should wait total ~0.4s")
        self.assertLess(elapsed_3, 0.45 + 0.05)

    async def test_burst_capacity(self):
        """
        Verify burst capacity behavior.
        """
        # Rate: 1 token/sec. Capacity: 3.
        limiter = RateLimiter(rate=1.0, capacity=3.0)

        # Should be able to acquire 3 immediately
        start = time.monotonic()
        await limiter.acquire()
        await limiter.acquire()
        await limiter.acquire()
        end = time.monotonic()

        self.assertLess(end - start, 0.05, "Should consume burst capacity immediately")

        # 4th should wait ~1s
        await limiter.acquire()
        end2 = time.monotonic()
        self.assertGreater(end2 - start, 0.9, "4th token should wait ~1s")

if __name__ == '__main__':
    unittest.main()
