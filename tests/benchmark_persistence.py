import asyncio
import time
import os
import json
from unittest.mock import AsyncMock
# We need to import AIManager class, but to simulate restart we just instantiate it again.
# The module-level 'ai_manager' instance is created on import, but we can ignore it and make our own.
from ai_manager import AIManager

CACHE_FILE = "ai_cache.json"

async def benchmark():
    # Cleanup previous run
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

    print("--- Benchmark: Persistent Caching ---")

    # 1. First Run: Populate Cache
    print("Step 1: First Run (Populating Cache)")
    ai1 = AIManager()

    # Mock slow response
    async def mock_slow_response(prompt, **kwargs):
        await asyncio.sleep(1.0)
        return '["Wolf", "Seer", "Villager"]'

    ai1.generate_response = AsyncMock(side_effect=mock_slow_response)

    player_count = 3
    existing_roles = ["Wolf", "Seer", "Villager"]

    start = time.time()
    res1 = await ai1.generate_role_template(player_count, existing_roles)
    print(f"Run 1 Time: {time.time() - start:.4f}s")

    # 2. Simulate Restart
    print("Step 2: Simulating Restart (New Instance)")
    del ai1

    # 3. Second Run: Check if Cache Persisted
    ai2 = AIManager()
    ai2.generate_response = AsyncMock(side_effect=mock_slow_response)

    start = time.time()
    res2 = await ai2.generate_role_template(player_count, existing_roles)
    duration = time.time() - start
    print(f"Run 2 Time: {duration:.4f}s")

    if duration < 0.1:
        print("RESULT: FAST (Persistence Working)")
    else:
        print("RESULT: SLOW (Persistence NOT Working)")

    # Cleanup
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)

if __name__ == "__main__":
    asyncio.run(benchmark())
