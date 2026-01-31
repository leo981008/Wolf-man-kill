import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import deque
import bot

class TestSpeakingPhase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.games = {}
        self.guild_id = 12345
        self.game = bot.get_game(self.guild_id)

        # Mock players
        self.p1 = MagicMock()
        self.p1.name = "P1"
        self.p1.id = 1
        self.p1.mention = "<@1>"
        self.p1.voice = MagicMock()
        self.p1.edit = AsyncMock()

        self.p2 = MagicMock()
        self.p2.name = "P2"
        self.p2.id = 2
        self.p2.mention = "<@2>"
        self.p2.voice = MagicMock()
        self.p2.edit = AsyncMock()

        self.game.players = [self.p1, self.p2]
        self.game.player_ids = {1: self.p1, 2: self.p2}
        self.game.player_id_map = {self.p1: 1, self.p2: 2}
        self.game.game_active = True

        self.ctx = MagicMock()
        self.ctx.guild.id = self.guild_id
        self.ctx.guild_id = self.guild_id
        self.ctx.send = AsyncMock()
        self.ctx.channel.set_permissions = AsyncMock()
        self.ctx.guild.default_role = MagicMock()

    async def test_perform_day_starts_speaking_phase(self):
        with patch('bot.mute_all_players', new_callable=AsyncMock) as mock_mute_all, \
             patch('bot.start_next_turn', new_callable=AsyncMock) as mock_start_turn, \
             patch('bot.secure_random.shuffle') as mock_shuffle, \
             patch('bot.check_game_over', new_callable=AsyncMock) as mock_check_over:

            # Ensure game active
            self.game.game_active = True

            # Since perform_day removes dead players, pass empty list
            await bot.perform_day(self.ctx, self.game, [])

            # Check flags
            self.assertTrue(self.game.speaking_active)
            self.assertIsNotNone(self.game.speaking_queue)
            self.assertEqual(len(self.game.speaking_queue), 2)

            # Check mocks
            mock_mute_all.assert_called_once()
            mock_start_turn.assert_called_once()

    async def test_done_command(self):
        # Setup speaking phase
        self.game.speaking_active = True
        self.game.current_speaker = self.p1
        self.game.speaking_queue = deque([self.p2])

        self.ctx.user = self.p1 # Interaction uses .user, not .author
        self.ctx.response.send_message = AsyncMock()

        with patch('bot.set_player_mute', new_callable=AsyncMock) as mock_set_mute, \
             patch('bot.start_next_turn', new_callable=AsyncMock) as mock_start_turn:

            await bot.done.callback(self.ctx)

            # Should mute current speaker
            mock_set_mute.assert_called_with(self.p1, True)
            # Should call next turn
            mock_start_turn.assert_called_once()

    async def test_vote_blocked_during_speaking(self):
        self.game.speaking_active = True
        self.ctx.user = self.p1
        self.ctx.response.send_message = AsyncMock()

        await bot.vote.callback(self.ctx, target_id="2")

        # Check that it sent a blocking message
        # In slash command it uses interaction.response.send_message with ephemeral=True
        # await interaction.response.send_message("請等待發言結束。", ephemeral=True)
        args = self.ctx.response.send_message.call_args[0][0]
        self.assertIn("等待發言結束", args)

        # Verify no vote recorded
        self.assertNotIn(self.p2, self.game.votes)

    async def test_vote_allowed_after_speaking(self):
        self.game.speaking_active = False
        self.ctx.user = self.p1
        self.ctx.response.send_message = AsyncMock()

        # Mock resolve_votes to avoid complexity
        with patch('bot.resolve_votes', new_callable=AsyncMock):
             await bot.vote.callback(self.ctx, target_id="2")

        # Verify vote recorded
        self.assertIn(self.p2, self.game.votes)

if __name__ == "__main__":
    unittest.main()
