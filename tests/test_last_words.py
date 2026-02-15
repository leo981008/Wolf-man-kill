import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
from ai_manager import ai_manager

class TestLastWords(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.games = {}
        self.guild_id = 12345
        self.game = bot.get_game(self.guild_id)
        self.game.game_active = True
        self.game.day_count = 1

        # Mock Channel
        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.channel.guild.id = self.guild_id
        self.channel.guild.default_role = MagicMock()
        self.channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
        self.channel.set_permissions = AsyncMock()

        # Mock Players
        self.ai_player = MagicMock()
        self.ai_player.name = "AI_Player"
        self.ai_player.id = 101
        self.ai_player.mention = "<@101>"
        self.ai_player.bot = True
        self.ai_player.send = AsyncMock()

        self.human_player = MagicMock()
        self.human_player.name = "Human_Player"
        self.human_player.id = 102
        self.human_player.mention = "<@102>"
        self.human_player.bot = False
        self.human_player.send = AsyncMock()

        self.game.players = [self.ai_player, self.human_player]
        self.game.player_ids = {101: self.ai_player, 102: self.human_player}
        self.game.roles = {self.ai_player: "狼人", self.human_player: "平民"}

    async def test_ai_last_words(self):
        """Test AI generating and sending last words when voted out."""
        # Mock dependencies
        with patch.object(ai_manager, 'get_ai_last_words', new_callable=AsyncMock) as mock_get_last_words, \
             patch('bot.check_game_over', new_callable=AsyncMock) as mock_check_game_over, \
             patch('asyncio.sleep', new_callable=AsyncMock):  # Skip sleep
            
            # Setup AI response
            mock_get_last_words.return_value = "I am a good wolf... I mean villager!"

            # Setup Vote Result (AI is voted out)
            self.game.votes = {self.ai_player: 2}
            self.game.voted_players = {self.ai_player, self.human_player}

            # Run resolve_votes
            await bot.resolve_votes(self.channel, self.game)

            # Verify AI method was called
            mock_get_last_words.assert_called_once()
            
            # Verify message sent to channel
            # We expect multiple calls to send (Vote result, Last words prompt, Last words content)
            # Check if one of the calls contains the last words
            sent_contents = [args[0] for args, _ in self.channel.send.call_args_list]
            self.assertTrue(any("I am a good wolf" in c for c in sent_contents))
            self.assertTrue(any("遺言" in c for c in sent_contents))

    async def test_human_last_words(self):
        """Test Human sending last words when voted out."""
        # Mock dependencies
        mock_msg = MagicMock()
        mock_msg.content = "This is my final message."
        mock_msg.author = self.human_player
        mock_msg.channel = self.channel

        with patch('bot.bot.wait_for', new_callable=AsyncMock) as mock_wait_for, \
             patch('bot.check_game_over', new_callable=AsyncMock) as mock_check_game_over:
            
            # Setup Human response
            mock_wait_for.return_value = mock_msg

            # Setup Vote Result (Human is voted out)
            self.game.votes = {self.human_player: 2}
            self.game.voted_players = {self.ai_player, self.human_player}

            # Run resolve_votes
            await bot.resolve_votes(self.channel, self.game)

            # Verify wait_for was called
            mock_wait_for.assert_called_once()
            
            # Verify message announced
            sent_contents = [args[0] for args, _ in self.channel.send.call_args_list]
            self.assertTrue(any("This is my final message" in c for c in sent_contents))

    async def test_no_last_words_on_game_over(self):
        """Verify Last Words are skipped if Game Over triggers."""
        
        async def side_effect_game_over(channel, game):
            game.game_active = False # End game
        
        with patch('bot.check_game_over', new_callable=AsyncMock) as mock_check_game_over, \
             patch('bot.request_last_words', new_callable=AsyncMock) as mock_req_last_words:
            
            mock_check_game_over.side_effect = side_effect_game_over

            # Setup Vote Result
            self.game.votes = {self.ai_player: 2}
            
            # Run resolve_votes
            await bot.resolve_votes(self.channel, self.game)

            # Verify request_last_words NOT called
            mock_req_last_words.assert_not_called()

if __name__ == "__main__":
    unittest.main()
