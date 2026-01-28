import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestBotFeatures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset global state before each test
        bot.players = []
        bot.gods = []
        bot.roles = {}
        bot.game_active = False

    async def test_god_and_join_switching(self):
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "User1"
        ctx.author.mention = "@User1"
        ctx.send = AsyncMock()

        # 1. Join as player
        await bot.join(ctx)
        self.assertIn(ctx.author, bot.players)
        self.assertNotIn(ctx.author, bot.gods)

        # 2. Switch to God
        await bot.god(ctx)
        self.assertNotIn(ctx.author, bot.players)
        self.assertIn(ctx.author, bot.gods)
        ctx.send.assert_called_with(f"{ctx.author.mention} 已加入天神組 (God)！")

        # 3. Switch back to Player
        await bot.join(ctx)
        self.assertIn(ctx.author, bot.players)
        self.assertNotIn(ctx.author, bot.gods)
        # Verify message says switched from god
        # We need to check if one of the calls was the specific message
        # But 'join' sends multiple messages potentially.
        # Let's check the logic state primarily.

    async def test_god_mid_game(self):
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "Quitter"
        ctx.author.mention = "@Quitter"
        ctx.send = AsyncMock()

        # Setup game active and user is player
        bot.game_active = True
        bot.players = [ctx.author]
        bot.gods = []

        await bot.god(ctx)

        self.assertNotIn(ctx.author, bot.players)
        self.assertIn(ctx.author, bot.gods)

        # Check if the specific message was sent among calls
        expected_msg = f"{ctx.author.mention} 已從玩家轉為天神。"
        found = any(call.args[0] == expected_msg for call in ctx.send.mock_calls)
        self.assertTrue(found, f"Message '{expected_msg}' not found in calls: {ctx.send.mock_calls}")

    async def test_start_preserves_gods(self):
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "Host"
        ctx.send = AsyncMock()
        ctx.author.send = AsyncMock()
        ctx.channel = MagicMock()
        ctx.channel.set_permissions = AsyncMock()
        ctx.guild = MagicMock()
        ctx.guild.default_role = MagicMock()

        # Setup: 1 God, 3 Players (Host is God)
        god_user = MagicMock()
        god_user.name = "GodUser"
        god_user.send = AsyncMock()

        bot.gods = [god_user]

        # Add 3 players so game can start
        p1 = MagicMock(); p1.name="P1"; p1.send=AsyncMock()
        p2 = MagicMock(); p2.name="P2"; p2.send=AsyncMock()
        p3 = MagicMock(); p3.name="P3"; p3.send=AsyncMock()
        bot.players = [p1, p2, p3]

        # Host runs start. Host is not in gods, not in players.
        # Logic says host should be added to gods.
        await bot.start(ctx)

        self.assertIn(god_user, bot.gods)
        self.assertIn(ctx.author, bot.gods) # Host added
        self.assertTrue(bot.game_active)

    async def test_die_command(self):
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.name = "GodUser"
        ctx.send = AsyncMock()

        # Setup game active
        bot.game_active = True

        # Setup players and gods
        victim = MagicMock()
        victim.name = "Victim"
        victim.mention = "@Victim"

        survivor = MagicMock()
        survivor.name = "Survivor"

        bot.players = [victim, survivor]
        bot.roles = {victim: "狼人", survivor: "平民"}

        bot.gods = [ctx.author]
        ctx.author.send = AsyncMock()

        # Mock MemberConverter to return victim
        with patch('discord.ext.commands.MemberConverter.convert', new=AsyncMock(return_value=victim)):
            await bot.die(ctx, target="Victim")

        # Verify victim removed
        self.assertNotIn(victim, bot.players)
        self.assertIn(survivor, bot.players)

        # Verify public message
        ctx.send.assert_called_with(f"👑 天神執行了處決，**{victim.name}** 已死亡。")

        # Verify private message to God
        # Should contain "狼人" (victim role) and "Survivor: 平民"
        call_args = ctx.author.send.call_args
        self.assertIsNotNone(call_args)
        msg = call_args[0][0]
        self.assertIn("**Victim** (狼人) 已死亡", msg)
        self.assertIn("Survivor: 平民", msg)

if __name__ == "__main__":
    unittest.main()
