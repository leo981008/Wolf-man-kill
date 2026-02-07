import pytest
import os
import asyncio
import json
from unittest.mock import MagicMock, patch, AsyncMock
from ai_manager import AIManager, ai_manager

@pytest.mark.asyncio
async def test_generate_role_template_gemini():
    # Clear cache to ensure call is made
    ai_manager.role_template_cache.clear()

    # Mocking _generate_with_gemini directly to simplify test of higher level logic
    with patch.object(ai_manager, '_generate_with_gemini', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '["狼人", "預言家", "平民"]'

        # Ensure provider is gemini
        ai_manager.provider = 'gemini'

        roles = await ai_manager.generate_role_template(3, ["狼人", "預言家", "平民"])

        assert roles == ["狼人", "預言家", "平民"]
        mock_gen.assert_called_once()

@pytest.mark.asyncio
async def test_get_ai_action_vote_gemini():
    with patch.object(ai_manager, '_generate_with_gemini', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '3' # Vote for player 3
        ai_manager.provider = 'gemini'

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "3"

@pytest.mark.asyncio
async def test_get_ai_action_abstain_gemini():
    with patch.object(ai_manager, '_generate_with_gemini', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 'no'
        ai_manager.provider = 'gemini'

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "no"

@pytest.mark.asyncio
async def test_generate_with_gemini_subprocess():
    """Test the actual subprocess call logic"""
    test_ai = AIManager()
    test_ai.provider = 'gemini'

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b'Mocked Response\n', b'')
        mock_process.returncode = 0

        mock_exec.return_value = mock_process

        response = await test_ai.generate_response("Test Prompt")

        assert response == "Mocked Response"

        # Verify call arguments
        mock_exec.assert_called_once_with(
            'gemini', '-p', 'Test Prompt',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

@pytest.mark.asyncio
async def test_generate_with_gemini_subprocess_error():
    """Test subprocess error handling"""
    test_ai = AIManager()
    test_ai.provider = 'gemini'

    with patch('asyncio.create_subprocess_exec') as mock_exec:
        # Create a mock process
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b'', b'Error occurred')
        mock_process.returncode = 1

        mock_exec.return_value = mock_process

        response = await test_ai.generate_response("Test Prompt")

        assert response == ""

@pytest.mark.asyncio
async def test_generate_narrative_caching():
    test_ai = AIManager()

    # Mock generate_response using AsyncMock since it's an async method
    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Cached Narrative"

        # First call
        res1 = await test_ai.generate_narrative("Type1", "Context1")
        assert res1 == "Cached Narrative"
        assert mock_gen.call_count == 1

        # Second call (should be cached)
        res2 = await test_ai.generate_narrative("Type1", "Context1")
        assert res2 == "Cached Narrative"
        assert mock_gen.call_count == 1

        # Different input (should call again)
        mock_gen.return_value = "New Narrative"
        res3 = await test_ai.generate_narrative("Type2", "Context2")
        assert res3 == "New Narrative"
        assert mock_gen.call_count == 2

@pytest.mark.asyncio
async def test_generate_narrative_cache_eviction_and_hashable():
    test_ai = AIManager()

    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Narrative"

        # Test unhashable context (dict)
        res1 = await test_ai.generate_narrative("Type", {"key": "value"})
        res2 = await test_ai.generate_narrative("Type", {"key": "value"})
        assert res1 == res2
        assert mock_gen.call_count == 1

        # Test eviction logic
        # We already have 1 item in cache.
        # Add 99 items to reach 100.
        for i in range(99):
             await test_ai.generate_narrative(f"Type{i}", "Context")

        assert len(test_ai.narrative_cache) == 100

        # Next call should trigger eviction (len >= 100)
        await test_ai.generate_narrative("Overflow", "Context")

        # Should maintain 100 items (evicted one, added one)
        assert len(test_ai.narrative_cache) == 100

        # Verify oldest item was evicted
        # The first item added was ("Type", str({"key": "value"}), "zh-TW")
        # Since we use OrderedDict, it should be gone.
        oldest_key = ("Type", str({"key": "value"}), "zh-TW")
        assert oldest_key not in test_ai.narrative_cache

        # Verify a newer item is still there
        newer_key = ("Type0", "Context", "zh-TW")
        assert newer_key in test_ai.narrative_cache

@pytest.mark.asyncio
async def test_generate_role_template_caching():
    # Use a separate cache file for testing to avoid interference
    with patch('ai_manager.CACHE_FILE', 'test_ai_cache.json'):
        if os.path.exists('test_ai_cache.json'):
            os.remove('test_ai_cache.json')

        test_ai = AIManager()

        with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = '["狼人", "預言家", "平民"]'

            roles = ["狼人", "預言家", "平民"]

            # First call
            res1 = await test_ai.generate_role_template(3, roles)
            assert res1 == roles
            assert mock_gen.call_count == 1

            # Second call (same roles, same count)
            res2 = await test_ai.generate_role_template(3, roles)
            assert res2 == roles
            assert mock_gen.call_count == 1

            # Third call (different roles order) - should still hit cache because we sort them
            res3 = await test_ai.generate_role_template(3, reversed(roles))
            assert res3 == roles
            assert mock_gen.call_count == 1

            # Fourth call (different count)
            mock_gen.return_value = '["狼人", "平民"]'
            res4 = await test_ai.generate_role_template(2, roles)
            assert res4 == ["狼人", "平民"]
            assert mock_gen.call_count == 2

        if os.path.exists('test_ai_cache.json'):
            os.remove('test_ai_cache.json')
