import pytest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from ai_manager import AIManager, ai_manager

@pytest.mark.asyncio
async def test_generate_role_template():
    # Mocking the model
    with patch('ai_manager.genai.GenerativeModel') as mock_model_cls:
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model

        # Manually set the model on our instance
        ai_manager.model = mock_model

        # Mock generate_content response
        mock_response = MagicMock()
        mock_response.parts = [1]
        mock_response.text = '["狼人", "預言家", "平民"]'

        mock_model.generate_content.return_value = mock_response

        roles = await ai_manager.generate_role_template(3, ["狼人", "預言家", "平民"])

        assert roles == ["狼人", "預言家", "平民"]

@pytest.mark.asyncio
async def test_get_ai_action_vote():
    with patch('ai_manager.genai.GenerativeModel') as mock_model_cls:
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        ai_manager.model = mock_model

        mock_response = MagicMock()
        mock_response.parts = [1]
        mock_response.text = '3' # Vote for player 3

        mock_model.generate_content.return_value = mock_response

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "3"

@pytest.mark.asyncio
async def test_get_ai_action_abstain():
    with patch('ai_manager.genai.GenerativeModel') as mock_model_cls:
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        ai_manager.model = mock_model

        mock_response = MagicMock()
        mock_response.parts = [1]
        mock_response.text = 'no'

        mock_model.generate_content.return_value = mock_response

        action = await ai_manager.get_ai_action("平民", "Vote", [1, 2, 3])
        assert action == "no"

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
            res4 = await test_ai.generate_role_template(2, roles) # roles passed here doesn't matter much for mock response validation if we don't strict check existing
            # But wait, logic checks if roles exist in existing_roles.
            # roles list has ["狼人", "預言家", "平民"]. generated has ["狼人", "平民"]. Both exist.
            assert res4 == ["狼人", "平民"]
            assert mock_gen.call_count == 2

        if os.path.exists('test_ai_cache.json'):
            os.remove('test_ai_cache.json')
