import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestBotStart(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Clear games before each test
        bot.games = {}

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_command_success(self, mock_perform_night):
        # Setup mocks
        ctx = MagicMock()
        ctx.user = MagicMock() # Interaction uses .user
        ctx.user.name = "TestHost"
        ctx.user.send = AsyncMock()

        ctx.response.send_message = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.send = AsyncMock()
        ctx.channel.set_permissions = AsyncMock()

        ctx.guild = MagicMock()
        ctx.guild.id = 12345
        ctx.guild_id = 12345 # Interaction has guild_id
        ctx.guild.default_role = MagicMock()

        # Followup mock
        ctx.followup.send = AsyncMock()

        # Mock players
        player1 = MagicMock()
        player1.name = "Player1"
        player1.send = AsyncMock()
        player1.mention = "<@P1>"

        player2 = MagicMock()
        player2.name = "Player2"
        player2.send = AsyncMock()
        player2.mention = "<@P2>"

        player3 = MagicMock()
        player3.name = "Player3"
        player3.send = AsyncMock()
        player3.mention = "<@P3>"

        # Set up bot state
        game = bot.get_game(ctx.guild_id)
        game.players = [player1, player2, player3]
        game.gods = [ctx.user]

        # Call start callback
        await bot.start.callback(ctx)

        # Check that game is active
        self.assertTrue(game.game_active)

        # Check that roles were assigned
        self.assertEqual(len(game.roles), 3)

        # Check that perform_night was called
        mock_perform_night.assert_called_once()

if __name__ == "__main__":
    unittest.main()
