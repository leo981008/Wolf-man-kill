import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

# Add the parent directory to sys.path to import bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot
from bot import handle_death_rattle, GameState

class TestHunterLogic(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.games = {}
        self.channel = AsyncMock()
        self.game = GameState()
        self.game.game_active = True
        
        # Player setup
        self.hunter = MagicMock()
        self.hunter.name = "Hunter"
        self.hunter.id = 1
        self.hunter.mention = "<@Hunter>"
        self.hunter.bot = False
        
        self.wolf = MagicMock()
        self.wolf.name = "Wolf"
        self.wolf.id = 2
        self.wolf.mention = "<@Wolf>"
        
        self.villager = MagicMock()
        self.villager.name = "Villager"
        self.villager.id = 3
        self.villager.mention = "<@Villager>"

        self.game.players = [self.hunter, self.wolf, self.villager]
        self.game.player_ids = {1: self.hunter, 2: self.wolf, 3: self.villager}
        self.game.player_id_map = {self.hunter: 1, self.wolf: 2, self.villager: 3}
        self.game.roles = {self.hunter: "獵人", self.wolf: "狼人", self.villager: "平民"}

    async def test_hunter_shoot_success(self):
        # Mock input to select Villager (ID 3)
        with patch('bot.request_dm_input', new_callable=AsyncMock) as mock_input, \
             patch('bot.announce_event', new_callable=AsyncMock) as mock_announce:
            
            mock_input.return_value = "3" # Select Villager
            
            dead_players = [self.hunter]
            # Call handle_death_rattle
            new_dead = await handle_death_rattle(self.channel, self.game, dead_players)
            
            # Verify input asked
            mock_input.assert_called_once()
            
            # Verify outcome
            self.assertIn(self.villager, new_dead)
            self.assertNotIn(self.villager, self.game.players)
            
            # Verify announcements
            # 1. Hunter activates
            # 2. Hunter shoots
            message_types = [call.args[2] for call in mock_announce.call_args_list]
            self.assertIn("獵人發動技能", message_types)
            self.assertIn("獵人開槍", message_types)

    async def test_hunter_poisoned_no_shoot(self):
        with patch('bot.request_dm_input', new_callable=AsyncMock) as mock_input, \
             patch('bot.announce_event', new_callable=AsyncMock) as mock_announce:
            
            dead_players = [self.hunter]
            # Hunter (ID 1) is poisoned
            new_dead = await handle_death_rattle(self.channel, self.game, dead_players, poison_victim_id=1)
            
            # Verify input NOT asked
            mock_input.assert_not_called()
            
            # Verify no new dead
            self.assertEqual(new_dead, [])
            self.assertIn(self.villager, self.game.players)
            
            # Verify announcement for failed shot
            args, _ = mock_announce.call_args
            self.assertIn("獵人死亡", args[2])
            self.assertIn("毒藥", args[3])

    async def test_hunter_refuse_shoot(self):
        with patch('bot.request_dm_input', new_callable=AsyncMock) as mock_input, \
             patch('bot.announce_event', new_callable=AsyncMock) as mock_announce:
            
            mock_input.return_value = "no" # Refuse
            
            dead_players = [self.hunter]
            new_dead = await handle_death_rattle(self.channel, self.game, dead_players)
            
            # Verify input asked
            mock_input.assert_called_once()
            
            # Verify no new dead
            self.assertEqual(new_dead, [])
            self.assertIn(self.villager, self.game.players)

if __name__ == "__main__":
    unittest.main()
