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
            game_context="現在是第 1 天白天。存活玩家: 8 人。昨晚死亡名單：無。",
            speech_history=[]
        )

        # Verify the prompt
        args, kwargs = mock_gen.call_args
        prompt = args[0]

        assert "你是本輪的「第 1 位」發言者" in prompt
        assert "在你之前「沒有任何玩家」發過言" in prompt
        assert "絕對禁止" in prompt
        assert "划水" in prompt

        # Anti-hallucination checks
        assert "嚴禁捏造資訊" in prompt
        assert "防止幻覺規則" in prompt
        assert "只能」使用本提示中明確提供的資訊" in prompt

        # New: Chain-of-Thought reasoning
        assert "思考步驟" in prompt
        assert "分析框架" in prompt

        # New: Phase-aware guide
        assert "當前階段策略" in prompt
        assert "前期" in prompt

@pytest.mark.asyncio
async def test_get_ai_speech_subsequent_speaker():
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mock Speech"

        history = ["Player1: Hello"]
        await ai.get_ai_speech(
            player_id=2,
            role="狼人",
            game_context="現在是第 1 天白天。存活玩家: 8 人。昨晚死亡名單：無。",
            speech_history=history
        )

        # Verify the prompt
        args, kwargs = mock_gen.call_args
        prompt = args[0]

        assert "你是本輪的「第 1 位」發言者" not in prompt
        assert "在你之前已經有 1 位玩家發言了" in prompt
        assert "Player1: Hello" in prompt
        assert "引用" in prompt or "站邊" in prompt

        # Anti-hallucination checks for subsequent speakers
        assert "嚴禁捏造資訊" in prompt
        assert "禁止聲稱任何玩家說了紀錄中沒有的話" in prompt
        assert "禁止虛構查驗結果" in prompt
        assert "防止幻覺規則" in prompt

        # New: Must have concrete conclusion
        assert "落點" in prompt

        # New: Chain-of-Thought
        assert "思考步驟" in prompt

@pytest.mark.asyncio
async def test_get_ai_action_anti_hallucination():
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "3"

        await ai.get_ai_action(
            role="狼人",
            game_context="夜晚行動。場上存活 8 人。",
            valid_targets=[1, 2, 3]
        )

        args, kwargs = mock_gen.call_args
        prompt = args[0]

        # Anti-hallucination checks for actions
        assert "行動規則" in prompt
        assert "只能」從上方列出的「可選擇目標」中選擇" in prompt
        assert "不可虛構理由" in prompt

        # New: Structured reasoning
        assert "決策分析" in prompt
        assert "分析框架" in prompt

        # New: Night action label
        assert "夜晚行動決策" in prompt

@pytest.mark.asyncio
async def test_get_ai_action_voting_phase():
    """Test that voting phase uses voting_guide instead of action_guide."""
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "2"

        await ai.get_ai_action(
            role="平民",
            game_context="第 1 天白天投票階段。場上存活 8 人。",
            valid_targets=[1, 2, 3],
            speech_history=["Player1: 我覺得 3 號很可疑"]
        )

        args, kwargs = mock_gen.call_args
        prompt = args[0]

        # Should use voting-specific label and guide
        assert "投票決策" in prompt
        assert "投票" in prompt

        # Still has structured reasoning
        assert "決策分析" in prompt
        assert "策略指導" in prompt

@pytest.mark.asyncio
async def test_generate_narrative_anti_hallucination():
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mock Narrative"

        await ai.generate_narrative(
            event_type="天黑",
            context="夜晚行動開始"
        )

        args, kwargs = mock_gen.call_args
        prompt = args[0]

        # Anti-hallucination checks for narrative
        assert "嚴格限制" in prompt
        assert "嚴禁透露任何玩家的身分" in prompt
        assert "嚴禁編造未發生的事件" in prompt

        # New: Atmosphere guidance
        assert "氛圍指導" in prompt

@pytest.mark.asyncio
async def test_generate_role_template_anti_hallucination():
    ai = AIManager()
    ai.role_template_cache.clear()  # Clear cache to ensure generate_response is called

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '["狼人", "預言家", "平民"]'

        await ai.generate_role_template(
            player_count=3,
            existing_roles=["狼人", "預言家", "平民"]
        )

        args, kwargs = mock_gen.call_args
        prompt = args[0]

        # Anti-hallucination checks for role template
        assert "不可發明新角色" in prompt
        assert "陣列長度必須恰好等於" in prompt
        assert "純 JSON 陣列" in prompt

@pytest.mark.asyncio
async def test_get_ai_speech_phase_detection():
    """Test that phase detection correctly maps day count to phase."""
    ai = AIManager()

    with patch.object(ai, 'generate_response', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Mock Speech"

        # Test early phase (Day 1)
        await ai.get_ai_speech(1, "平民", "現在是第 1 天白天。存活玩家: 8 人。", [])
        prompt_day1 = mock_gen.call_args[0][0]
        assert "前期" in prompt_day1

        # Test mid phase (Day 3)
        await ai.get_ai_speech(1, "平民", "現在是第 3 天白天。存活玩家: 5 人。", [])
        prompt_day3 = mock_gen.call_args[0][0]
        assert "中期" in prompt_day3

        # Test late phase (Day 5)
        await ai.get_ai_speech(1, "平民", "現在是第 5 天白天。存活玩家: 3 人。", [])
        prompt_day5 = mock_gen.call_args[0][0]
        assert "殘局" in prompt_day5

@pytest.mark.asyncio
async def test_phase_name_helper():
    """Test the _get_phase_name helper method."""
    ai = AIManager()

    assert ai._get_phase_name("現在是第 1 天白天。") == "early"
    assert ai._get_phase_name("現在是第 2 天白天。") == "early"
    assert ai._get_phase_name("現在是第 3 天白天。") == "mid"
    assert ai._get_phase_name("現在是第 4 天白天。") == "mid"
    assert ai._get_phase_name("現在是第 5 天白天。") == "late"
    assert ai._get_phase_name("現在是第 10 天白天。") == "late"
    assert ai._get_phase_name("夜晚行動") == "early"  # Default when no day info
