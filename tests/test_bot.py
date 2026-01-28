import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestBotStart(unittest.IsolatedAsyncioTestCase):
    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_command_sends_role_descriptions(self, mock_perform_night):
        # Setup mocks
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "TestHost"
        ctx.author.send = AsyncMock()
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.default_role = MagicMock()

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
        # Reset globals
        bot.players = [player1, player2, player3]
        bot.game_active = False
        bot.roles = {}
        bot.votes = {}

        # Call start
        await bot.start(ctx)

        # Verify ctx.send was called
        # We expect multiple calls.
        # 1. "Game Started!..."
        # 2. "Darkness..."

        # We want to check if any of the calls contain "本局角色功能說明"
        found_role_description = False
        messages = []
        for call_args in ctx.send.call_args_list:
            args, kwargs = call_args
            msg = args[0]
            messages.append(msg)
            if "本局角色功能說明" in msg:
                found_role_description = True
                print("Found role description message:")
                print(msg)

        if not found_role_description:
            print("Role description message NOT found.")
            print("Messages sent:")
            for msg in messages:
                print(f"- {msg}")

        # Assertions
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
        # 3-player game shouldn't have these
        self.assertNotIn("女巫", description_msg)
        self.assertNotIn("獵人", description_msg)

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_command_sends_attribution(self, mock_perform_night):
        # Setup mocks
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "TestHost"
        ctx.author.send = AsyncMock()
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.default_role = MagicMock()

        # Mock players (Need at least 3 to start)
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
        bot.players = [player1, player2, player3]
        bot.game_active = False
        bot.roles = {}
        bot.gods = [ctx.author] # Author must be god to start

        # Call start
        await bot.start(ctx)

        # Check for attribution in any of the sent messages
        found_attribution = False
        for call_args in ctx.send.call_args_list:
            args, kwargs = call_args
            msg = args[0]
            if "(資料來源: [狼人殺百科](https://lrs.fandom.com/zh/wiki/局式), CC-BY-SA)" in msg:
                found_attribution = True
                break

        self.assertTrue(found_attribution, "Attribution message should be present in bot output")

if __name__ == "__main__":
    unittest.main()
