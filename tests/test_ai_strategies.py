import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from ai_manager import AIManager
from ai_strategies import ROLE_STRATEGIES

@pytest.mark.asyncio
async def test_speech_prompt_integration():
    """
    Verifies that the prompt sent to the model contains the role-specific strategy.
    """
    test_ai = AIManager()

    # We want to intercept the prompt, so we mock generate_response
    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mocked Speech"

        # Test Case 1: Seer (預言家)
        role = "預言家"
        strategy = ROLE_STRATEGIES[role]
        await test_ai.get_ai_speech(1, role, "Game Start")

        # Capture the call arguments
        call_args = mock_gen.call_args[0][0]

        # Assertions
        assert f"你的發言風格應該是：{strategy['speech_style']}" in call_args
        assert f"你的主要目標是：{strategy['objective']}" in call_args
        assert strategy['speech_guide'] in call_args

        # Test Case 2: Werewolf (狼人)
        role = "狼人"
        strategy = ROLE_STRATEGIES[role]
        await test_ai.get_ai_speech(2, role, "Night falls")

        call_args = mock_gen.call_args[0][0]
        assert f"你的發言風格應該是：{strategy['speech_style']}" in call_args
        assert "深水狼" in call_args  # Part of the guide
        assert "悍跳狼" in call_args

@pytest.mark.asyncio
async def test_action_prompt_integration():
    """
    Verifies that the prompt sent to the model contains action guidance.
    """
    test_ai = AIManager()

    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "1"

        role = "女巫"
        strategy = ROLE_STRATEGIES[role]

        await test_ai.get_ai_action(role, "Night", [1, 2, 3])

        call_args = mock_gen.call_args[0][0]

        assert f"策略建議：{strategy['action_guide']}" in call_args

@pytest.mark.asyncio
async def test_fallback_for_unknown_role():
    """
    Verifies that unknown roles don't crash and use defaults.
    """
    test_ai = AIManager()

    with patch.object(test_ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Speech"

        role = "UnknownRole"

        await test_ai.get_ai_speech(3, role, "Context")

        call_args = mock_gen.call_args[0][0]
        # Should rely on .get defaults
        assert "你的發言風格應該是：自然" in call_args
