import pytest
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
