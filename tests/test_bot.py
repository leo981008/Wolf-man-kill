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
    async def test_start_command_sends_role_descriptions(self, mock_perform_night):
        # Setup mocks
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "TestHost"
        ctx.author.send = AsyncMock()
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.send = AsyncMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 12345
        ctx.guild_id = 12345 # Fix interaction.guild_id access
        ctx.guild.default_role = MagicMock()

        # Mock interaction response
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()

        # Mock players
        player1 = MagicMock()
        player1.name = "Player1"
        player1.send = AsyncMock()

        player2 = MagicMock()
        player2.name = "Player2"
        player2.send = AsyncMock()

        player3 = MagicMock()
        player3.name = "Player3"
        player3.send = AsyncMock()

        # Set up bot state
        game = bot.get_game(ctx.guild.id)
        game.players = [player1, player2, player3]
        game.gods = [ctx.author] # Host needs to be god or player to start without erroring if not in list?
        # Actually start command handles adding host to gods if not present.

        ctx.user = ctx.author # Fix interaction.user access

        # Call start
        await bot.start.callback(ctx)

        # Verify ctx.channel.send was called
        found_role_description = False
        messages = []

        # Check channel messages
        for call_args in ctx.channel.send.call_args_list:
            args, kwargs = call_args
            msg = args[0]
            messages.append(msg)
            if "本局角色功能說明" in msg:
                found_role_description = True

        self.assertTrue(found_role_description, "Role description should be sent")

        # Verify content
        description_msg = ""
        for msg in messages:
            if "本局角色功能說明" in msg:
                description_msg = msg
                break

        self.assertIn("狼人", description_msg)
        self.assertIn("預言家", description_msg)
        self.assertIn("平民", description_msg)

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_command_sends_attribution(self, mock_perform_night):
        # Setup mocks
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "TestHost"
        ctx.author.send = AsyncMock()
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.send = AsyncMock() # Ensure this is mocked
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 12345
        ctx.guild_id = 12345 # Fix interaction.guild_id access
        ctx.guild.default_role = MagicMock()

        # Mock interaction response
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()

        # Mock players
        player1 = MagicMock()
        player1.name = "Player1"
        player1.send = AsyncMock()
        player2 = MagicMock()
        player2.name = "Player2"
        player2.send = AsyncMock()
        player3 = MagicMock()
        player3.name = "Player3"
        player3.send = AsyncMock()

        # Set up bot state
        game = bot.get_game(ctx.guild.id)
        game.players = [player1, player2, player3]
        game.gods = [ctx.author]

        ctx.user = ctx.author

        # Call start
        await bot.start.callback(ctx)

        # Check for attribution
        found_attribution = False
        for call_args in ctx.channel.send.call_args_list:
            args, kwargs = call_args
            msg = args[0]
            if "(資料來源: [狼人殺百科](https://lrs.fandom.com/zh/wiki/局式), CC-BY-SA)" in msg:
                found_attribution = True
                break

        self.assertTrue(found_attribution, "Attribution message should be present")

if __name__ == "__main__":
    unittest.main()
