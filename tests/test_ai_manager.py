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

    # Mocking generate_response directly to simplify test of higher level logic
    with patch.object(ai_manager, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '["狼人", "預言家", "平民"]'

        # Ensure provider is gemini
        ai_manager.provider = 'gemini'

        roles = await ai_manager.generate_role_template(3, ["狼人", "預言家", "平民"])

        assert roles == ["狼人", "預言家", "平民"]
        mock_gen.assert_called_once()

@pytest.mark.asyncio
async def test_get_ai_action_vote_gemini():
    with patch.object(ai_manager, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '3' # Vote for player 3
        ai_manager.provider = 'gemini'

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "3"

@pytest.mark.asyncio
async def test_get_ai_action_abstain_gemini():
    with patch.object(ai_manager, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = 'no'
        ai_manager.provider = 'gemini'

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "no"

@pytest.mark.asyncio
async def test_generate_with_gemini_api_success():
    """Test the actual Gemini REST API call logic (success path)"""
    test_ai = AIManager()
    test_ai.provider = 'gemini-api'
    test_ai.gemini_api_key = 'fake-key'

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Mocked REST Response"}]
                }
            }
        ]
    })
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_response
    mock_session.post.return_value = mock_cm

    with patch.object(test_ai, 'get_session', new_callable=AsyncMock) as mock_get_sess:
        mock_get_sess.return_value = mock_session

        response = await test_ai.generate_response("Test Prompt")

        assert response == "Mocked REST Response"
        # We can verify that it was called once with the correct URL
        mock_session.post.assert_called_once()
        args, kwargs = mock_session.post.call_args
        assert "generativelanguage.googleapis.com" in args[0]

@pytest.mark.asyncio
async def test_generate_with_gemini_api_error():
    """Test the actual Gemini REST API call logic (error/429 retry path)"""
    test_ai = AIManager()
    test_ai.provider = 'gemini-api'
    test_ai.gemini_api_key = 'fake-key'
    # Set high rate limits so it executes quickly in test
    test_ai.rate_limiter.rate = 1000.0
    test_ai.rate_limiter.capacity = 1000.0

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Internal Error")
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_response
    mock_session.post.return_value = mock_cm

    with patch.object(test_ai, 'get_session', new_callable=AsyncMock) as mock_get_sess:
        mock_get_sess.return_value = mock_session

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

@pytest.mark.asyncio
async def test_get_ai_action_invalid_target_fallback():
    test_ai = AIManager()
    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        # AI returns '4' which is NOT in valid_targets [1, 2, 3]
        mock_gen.return_value = '4'
        action = await test_ai.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "no"

        # AI returns '2' which is in valid_targets [1, 2, 3]
        mock_gen.return_value = '2'
        action = await test_ai.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "2"

@pytest.mark.asyncio
async def test_get_ai_action_batch_invalid_target_fallback():
    test_ai = AIManager()
    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        # AI returns JSON where AI_1 votes for '4' (invalid) and AI_2 votes for '2' (valid)
        mock_gen.return_value = '{"AI_1": "4", "AI_2": "2"}'
        players_info = {"AI_1": "平民", "AI_2": "狼人"}
        results = await test_ai.get_ai_action_batch(players_info, "Vote", [1, 2, 3])
        assert results["AI_1"] == "no"
        assert results["AI_2"] == "2"

