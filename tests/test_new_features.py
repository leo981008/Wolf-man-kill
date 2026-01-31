import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestBotFeatures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset games
        bot.games = {}

    async def test_god_and_join_switching(self):
        ctx = MagicMock()
        ctx.guild.id = 1001
        ctx.guild_id = 1001
        ctx.author = MagicMock()
        ctx.author.name = "User1"
        ctx.author.mention = "@User1"
        ctx.user = ctx.author
        ctx.send = AsyncMock()
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.channel.send = AsyncMock()

        game = bot.get_game(ctx.guild.id)

        # 1. Join as player
        await bot.join.callback(ctx)
        self.assertIn(ctx.author, game.players)
        self.assertNotIn(ctx.author, game.gods)

        # 2. Switch to God
        await bot.god.callback(ctx)
        self.assertNotIn(ctx.author, game.players)
        self.assertIn(ctx.author, game.gods)

        # Check if correct message sent
        # We look for "User1 已加入天神組"
        found = any("已加入天神組" in str(call) for call in ctx.response.send_message.mock_calls)
        self.assertTrue(found)

        # 3. Switch back to Player
        await bot.join.callback(ctx)
        self.assertIn(ctx.author, game.players)
        self.assertNotIn(ctx.author, game.gods)

    async def test_god_mid_game(self):
        ctx = MagicMock()
        ctx.guild.id = 1001
        ctx.guild_id = 1001
        ctx.author = MagicMock()
        ctx.author.name = "Quitter"
        ctx.author.mention = "@Quitter"
        ctx.user = ctx.author
        ctx.send = AsyncMock()
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.channel.send = AsyncMock()

        game = bot.get_game(ctx.guild.id)
        game.game_active = True
        game.players = [ctx.author]
        game.gods = []

        await bot.god.callback(ctx)

        self.assertNotIn(ctx.author, game.players)
        self.assertIn(ctx.author, game.gods)

        # Check if the specific message was sent (to channel)
        # In bot.god: await interaction.channel.send(f"{interaction.user.mention} 已從玩家轉為天神。")
        expected_msg = f"{ctx.author.mention} 已從玩家轉為天神。"
        found = any(call.args[0] == expected_msg for call in ctx.channel.send.mock_calls)
        self.assertTrue(found)

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_preserves_gods(self, mock_night):
        ctx = MagicMock()
        ctx.guild.id = 1001
        ctx.guild_id = 1001
        ctx.author = MagicMock()
        ctx.author.name = "Host"
        ctx.user = ctx.author
        ctx.send = AsyncMock()
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.followup = MagicMock()
        ctx.followup.send = AsyncMock()
        ctx.author.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.send = AsyncMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild.default_role = MagicMock()

        game = bot.get_game(ctx.guild.id)

        # Setup: 1 God, 3 Players (Host is God)
        god_user = MagicMock()
        god_user.name = "GodUser"
        god_user.send = AsyncMock()

        game.gods = [god_user]

        # Add 3 players so game can start
        p1 = MagicMock(); p1.name="P1"; p1.send=AsyncMock()
        p2 = MagicMock(); p2.name="P2"; p2.send=AsyncMock()
        p3 = MagicMock(); p3.name="P3"; p3.send=AsyncMock()
        game.players = [p1, p2, p3]

        # Host runs start.
        await bot.start.callback(ctx)

        self.assertIn(god_user, game.gods)
        self.assertIn(ctx.author, game.gods) # Host added
        self.assertTrue(game.game_active)

    async def test_die_command(self):
        ctx = MagicMock()
        ctx.guild.id = 1001
        ctx.guild_id = 1001
        ctx.channel = MagicMock()
        ctx.channel.send = AsyncMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild.default_role = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "GodUser"
        ctx.user = ctx.author
        # Explicitly set permissions to False to test creator logic, or True for Admin
        ctx.author.guild_permissions.administrator = False
        ctx.send = AsyncMock()
        ctx.response = MagicMock()
        ctx.response.send_message = AsyncMock()
        ctx.author.send = AsyncMock()

        game = bot.get_game(ctx.guild.id)
        game.game_active = True
        game.creator = ctx.author # Make author the creator

        # Setup players and gods
        victim = MagicMock()
        victim.name = "Victim"
        victim.mention = "@Victim"
        victim.id = 999

        survivor = MagicMock()
        survivor.name = "Survivor"
        survivor.id = 888

        game.players = [victim, survivor]
        game.roles = {victim: "狼人", survivor: "平民"}
        game.player_ids = {999: victim, 888: survivor} # Populate IDs

        game.gods = [ctx.author]

        await bot.die.callback(ctx, target="999")

        # Verify victim removed
        self.assertNotIn(victim, game.players)
        self.assertIn(survivor, game.players)

        # Verify public message (response)
        expected_msg = f"👑 天神執行了處決，**{victim.name}** 已死亡。"
        found = any(call.args[0] == expected_msg for call in ctx.response.send_message.mock_calls)
        self.assertTrue(found)

if __name__ == "__main__":
    unittest.main()
