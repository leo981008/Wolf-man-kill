import pytest
from unittest.mock import AsyncMock, patch
from ai_manager import AIManager

@pytest.mark.asyncio
async def test_get_ai_speech_first_speaker():
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mock Speech"

        await ai.get_ai_speech(
            player_id=1,
            role="平民",
            game_context="Day 1",
            speech_history=[]
        )

        # Verify the prompt
        args, kwargs = mock_gen.call_args
        prompt = args[0]

        assert "你是本輪的「第 1 位」發言者" in prompt
        assert "在你之前「沒有任何玩家」發過言" in prompt
        assert "絕對禁止" in prompt
        assert "划水" in prompt

@pytest.mark.asyncio
async def test_get_ai_speech_subsequent_speaker():
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mock Speech"

        history = ["Player1: Hello"]
        await ai.get_ai_speech(
            player_id=2,
            role="狼人",
            game_context="Day 1",
            speech_history=history
        )

        # Verify the prompt
        args, kwargs = mock_gen.call_args
        prompt = args[0]

        assert "你是本輪的「第 1 位」發言者" not in prompt
        assert "在你之前已經有 1 位玩家發言了" in prompt
        assert "Player1: Hello" in prompt
        assert "請仔細分析前面玩家的發言" in prompt
