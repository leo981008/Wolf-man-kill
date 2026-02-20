import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
from bot import AIPlayer
import game_objects

class TestBotFeatures(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Reset games
        bot.games = {}
        game_objects.games.clear()

    async def test_god_and_join_switching(self):
        interaction = MagicMock()
        interaction.guild_id = 1001
        interaction.user = MagicMock()
        interaction.user.name = "User1"
        interaction.user.mention = "@User1"
        interaction.response.send_message = AsyncMock()
        interaction.channel.send = AsyncMock()

        game = bot.get_game(interaction.guild_id)

        # 1. Join as player
        await bot.join.callback(interaction)
        self.assertIn(interaction.user, game.players)
        self.assertNotIn(interaction.user, game.gods)

        # 2. Switch to God
        await bot.god.callback(interaction)
        self.assertNotIn(interaction.user, game.players)
        self.assertIn(interaction.user, game.gods)

        # 3. Switch back to Player
        await bot.join.callback(interaction)
        self.assertIn(interaction.user, game.players)
        self.assertNotIn(interaction.user, game.gods)

    async def test_god_mid_game(self):
        interaction = MagicMock()
        interaction.guild_id = 1001
        interaction.user = MagicMock()
        interaction.user.name = "Quitter"
        interaction.user.mention = "@Quitter"
        interaction.response.send_message = AsyncMock()
        interaction.channel.send = AsyncMock()

        game = bot.get_game(interaction.guild_id)
        game.game_active = True
        game.players = [interaction.user]
        game.gods = []

        await bot.god.callback(interaction)

        self.assertNotIn(interaction.user, game.players)
        self.assertIn(interaction.user, game.gods)

        # Check if the specific message was sent via channel.send
        expected_msg = f"{interaction.user.mention} 已從玩家轉為天神。"
        found = any(call.args[0] == expected_msg for call in interaction.channel.send.mock_calls)
        self.assertTrue(found)

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_host_not_player_becomes_god(self, mock_night):
        """Host 不在玩家列表中，應自動成為天神"""
        interaction = MagicMock()
        interaction.guild_id = 1001
        interaction.user = MagicMock()
        interaction.user.name = "Host"
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.channel.send = AsyncMock()
        interaction.user.send = AsyncMock()
        interaction.guild.default_role = MagicMock()

        game = bot.get_game(interaction.guild_id)

        # Setup: 1 God, 3 Players (Host is NOT a player)
        god_user = MagicMock()
        god_user.name = "GodUser"
        god_user.send = AsyncMock()

        game.gods = [god_user]

        # Add 3 players so game can start
        p1 = MagicMock(); p1.name="P1"; p1.send=AsyncMock()
        p2 = MagicMock(); p2.name="P2"; p2.send=AsyncMock()
        p3 = MagicMock(); p3.name="P3"; p3.send=AsyncMock()
        game.players = [p1, p2, p3]

        # Host runs start (Host is not a player).
        await bot.start.callback(interaction)

        self.assertIn(god_user, game.gods)
        self.assertIn(interaction.user, game.gods)  # Host auto-added to gods
        self.assertNotIn(interaction.user, game.players)
        self.assertTrue(game.game_active)

    @patch('bot.perform_night', new_callable=AsyncMock)
    async def test_start_host_is_player_stays_player(self, mock_night):
        """Host 已在玩家列表中，不應被強制轉為天神"""
        interaction = MagicMock()
        interaction.guild_id = 1001
        interaction.user = MagicMock()
        interaction.user.name = "Host"
        interaction.response.send_message = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.channel.send = AsyncMock()
        interaction.user.send = AsyncMock()
        interaction.guild.default_role = MagicMock()

        game = bot.get_game(interaction.guild_id)

        # Add 3 players including Host
        p1 = MagicMock(); p1.name="P1"; p1.send=AsyncMock()
        p2 = MagicMock(); p2.name="P2"; p2.send=AsyncMock()
        game.players = [interaction.user, p1, p2]

        # Host runs start (Host IS a player).
        await bot.start.callback(interaction)

        self.assertIn(interaction.user, game.players)  # Host stays as player
        self.assertNotIn(interaction.user, game.gods)  # Host NOT added to gods
        self.assertTrue(game.game_active)

    async def test_die_command(self):
        interaction = MagicMock()
        interaction.guild_id = 1001
        interaction.channel.set_permissions = AsyncMock()
        interaction.guild.default_role = MagicMock()
        interaction.user = MagicMock()
        interaction.user.name = "GodUser"
        # Explicitly set permissions to False to test creator logic
        interaction.user.guild_permissions.administrator = False
        interaction.response.send_message = AsyncMock()
        interaction.channel.send = AsyncMock()

        game = bot.get_game(interaction.guild_id)
        game.game_active = True
        game.creator = interaction.user # Make author the creator

        # Setup players and gods
        victim = MagicMock()
        victim.name = "Victim"
        victim.mention = "@Victim"
        # We need to set up player_ids map because die command uses ID
        game.player_ids[1] = victim
        game.player_id_map[victim] = 1

        survivor = MagicMock()
        survivor.name = "Survivor"
        game.player_ids[2] = survivor
        game.player_id_map[survivor] = 2

        game.players = [victim, survivor]
        game.roles = {victim: "狼人", survivor: "平民"}

        game.gods = [interaction.user]

        # Call die with ID "1"
        await bot.die.callback(interaction, target="1")

        # Verify victim removed
        self.assertNotIn(victim, game.players)
        self.assertIn(survivor, game.players)

        # Verify public message
        expected_msg = f"👑 天神執行了處決，**{victim.name}** 已死亡。"
        found = any(call.args[0] == expected_msg for call in interaction.response.send_message.mock_calls)
        self.assertTrue(found)

if __name__ == "__main__":
    unittest.main()
