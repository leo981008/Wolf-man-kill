import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from bot import GameState, WerewolfBot, get_game
import bot

class TestSpeechHistory:
    @pytest.fixture
    def game(self):
        return GameState()

    def test_game_init(self, game):
        assert hasattr(game, 'speech_history')
        assert game.speech_history == []

    def test_game_reset(self, game):
        game.speech_history.append("Some speech")
        game.reset()
        assert game.speech_history == []

    @pytest.mark.asyncio
    async def test_on_message_captures_speech(self):
        # Setup
        mock_msg = MagicMock()
        mock_msg.author.bot = False
        mock_msg.author.name = "Player1"
        mock_msg.content = "Hello world"
        mock_msg.guild.id = 123

        # Setup Game
        game = bot.get_game(123)
        game.game_active = True
        game.speaking_active = True
        game.current_speaker = mock_msg.author
        game.speech_history = []

        # We need to mock bot.process_commands to avoid it doing anything
        with patch.object(bot.bot, 'process_commands', new_callable=AsyncMock):
             # Trigger
             await bot.on_message(mock_msg)

        # Verify
        assert len(game.speech_history) == 1
        assert game.speech_history[0] == "Player1: Hello world"

    @pytest.mark.asyncio
    async def test_on_message_ignores_other_speakers(self):
        # Setup
        mock_msg = MagicMock()
        mock_msg.author.bot = False
        mock_msg.author.name = "Player2"
        mock_msg.content = "Interrupting"
        mock_msg.guild.id = 123

        # Setup Game
        game = bot.get_game(123)
        game.game_active = True
        game.speaking_active = True
        # Current speaker is someone else
        game.current_speaker = MagicMock()
        game.speech_history = []

        with patch.object(bot.bot, 'process_commands', new_callable=AsyncMock):
             await bot.on_message(mock_msg)

        # Verify
        assert len(game.speech_history) == 0

from ai_manager import ai_manager, AIManager
import os

class TestOllamaSupport:
    @pytest.mark.asyncio
    async def test_generate_with_ollama(self):
        # Setup mock for aiohttp
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"response": "Ollama says hi"}

            # Context manager mock
            mock_post.return_value.__aenter__.return_value = mock_response

            # Set provider to ollama
            ai_manager.provider = 'ollama'
            ai_manager.ollama_host = 'http://test-host'
            ai_manager.ollama_model = 'test-model'

            # Run
            response = await ai_manager.generate_response("Test prompt")

            # Verify
            assert response == "Ollama says hi"
            mock_post.assert_called_with(
                'http://test-host/api/generate',
                json={'model': 'test-model', 'prompt': 'Test prompt', 'stream': False}
            )

    @pytest.mark.asyncio
    async def test_get_ai_speech_includes_history(self):
        speech_history = ["P1: Hi", "P2: Hello"]

        # Mock generate_response to capture prompt
        with patch.object(ai_manager, 'generate_response', return_value="AI Speech") as mock_gen:
            await ai_manager.get_ai_speech(1, "Villager", "Context", speech_history)

            # Verify prompt contains history
            args, _ = mock_gen.call_args
            prompt = args[0]
            assert "本輪發言紀錄：" in prompt
            assert "P1: Hi" in prompt
            assert "P2: Hello" in prompt
