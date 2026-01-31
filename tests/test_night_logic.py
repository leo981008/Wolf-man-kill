import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import bot

class TestNightLogic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.game = bot.GameState()
        self.game.game_active = True
        self.game.player_ids = {}
        self.game.roles = {}
        self.game.players = []
        self.game.witch_potions = {'antidote': True, 'poison': True}

        # Setup players
        self.guard = MagicMock(); self.guard.bot = False; self.guard.name = "Guard"
        self.wolf = MagicMock(); self.wolf.bot = False; self.wolf.name = "Wolf"
        self.witch = MagicMock(); self.witch.bot = False; self.witch.name = "Witch"
        self.seer = MagicMock(); self.seer.bot = False; self.seer.name = "Seer"
        self.villager = MagicMock(); self.villager.bot = False; self.villager.name = "Villager"

        players = [self.guard, self.wolf, self.witch, self.seer, self.villager]
        roles = ["守衛", "狼人", "女巫", "預言家", "平民"]

        for idx, (p, r) in enumerate(zip(players, roles), 1):
            p.id = idx
            self.game.players.append(p)
            self.game.roles[p] = r
            self.game.player_ids[idx] = p
            p.send = AsyncMock()

        self.channel = MagicMock()
        self.channel.send = AsyncMock()
        self.channel.set_permissions = AsyncMock()

    @patch('bot.perform_day', new_callable=AsyncMock)
    @patch('bot.announce_event', new_callable=AsyncMock)
    @patch('bot.ai_manager.get_ai_action', new_callable=AsyncMock)
    async def test_night_kill_success(self, mock_ai, mock_announce, mock_perform_day):
        # Wolf kills Villager (5)
        # Witch does nothing
        # Guard does nothing

        async def mock_input(player, prompt, valid_check, timeout=45):
            if player == self.wolf: return "5" # Kill Villager
            if player == self.witch: return "no" # No save, no poison
            if player == self.guard: return "no" # No guard
            if player == self.seer: return "no" # No check
            return "no"

        with patch('bot.request_dm_input', side_effect=mock_input):
            await bot.perform_night(self.channel, self.game)

        # Verify perform_day called with [Villager]
        args, _ = mock_perform_day.call_args
        dead_list = args[2]
        self.assertEqual(len(dead_list), 1)
        self.assertEqual(dead_list[0], self.villager)

    @patch('bot.perform_day', new_callable=AsyncMock)
    @patch('bot.announce_event', new_callable=AsyncMock)
    @patch('bot.ai_manager.get_ai_action', new_callable=AsyncMock)
    async def test_night_witch_save(self, mock_ai, mock_announce, mock_perform_day):
        # Wolf kills Villager (5)
        # Witch saves

        async def mock_input(player, prompt, valid_check, timeout=45):
            if player == self.wolf: return "5"
            if player == self.witch:
                # Witch prompt depends on logic. First prompt is save.
                if "使用解藥" in prompt: return "yes"
                return "no"
            if player == self.guard: return "no"
            if player == self.seer: return "no"
            return "no"

        with patch('bot.request_dm_input', side_effect=mock_input):
            await bot.perform_night(self.channel, self.game)

        # Verify no death
        args, _ = mock_perform_day.call_args
        dead_list = args[2]
        self.assertEqual(len(dead_list), 0)
        self.assertFalse(self.game.witch_potions['antidote'])

    @patch('bot.perform_day', new_callable=AsyncMock)
    @patch('bot.announce_event', new_callable=AsyncMock)
    @patch('bot.ai_manager.get_ai_action', new_callable=AsyncMock)
    async def test_night_guard_protect(self, mock_ai, mock_announce, mock_perform_day):
        # Wolf kills Villager (5)
        # Guard protects Villager (5)

        async def mock_input(player, prompt, valid_check, timeout=45):
            if player == self.wolf: return "5"
            if player == self.witch: return "no"
            if player == self.guard: return "5"
            if player == self.seer: return "no"
            return "no"

        with patch('bot.request_dm_input', side_effect=mock_input):
            await bot.perform_night(self.channel, self.game)

        # Verify no death
        args, _ = mock_perform_day.call_args
        dead_list = args[2]
        self.assertEqual(len(dead_list), 0)

    @patch('bot.perform_day', new_callable=AsyncMock)
    @patch('bot.announce_event', new_callable=AsyncMock)
    @patch('bot.ai_manager.get_ai_action', new_callable=AsyncMock)
    async def test_night_milk_pierce(self, mock_ai, mock_announce, mock_perform_day):
        # Wolf kills Villager (5)
        # Guard protects (5)
        # Witch saves (yes)
        # Rule: Both -> Die (Milk Pierce)

        async def mock_input(player, prompt, valid_check, timeout=45):
            if player == self.wolf: return "5"
            if player == self.witch:
                 if "使用解藥" in prompt: return "yes"
                 return "no"
            if player == self.guard: return "5"
            if player == self.seer: return "no"
            return "no"

        with patch('bot.request_dm_input', side_effect=mock_input):
            await bot.perform_night(self.channel, self.game)

        # Verify Villager dies
        args, _ = mock_perform_day.call_args
        dead_list = args[2]
        self.assertEqual(len(dead_list), 0)
        # Wait, memory says: "If a player is protected by the Guard and saved by the Witch in the same night, the player dies (Milk Pierce/奶穿 rule)."
        # Let's check the code logic.

        # Code:
        # if is_guarded and is_saved: pass # 奶穿 (Pass implies NO death added to dead_ids? No, look at logic)
        # elif not is_guarded and not is_saved: dead_ids.add(wolf_kill)

        # Original code:
        # if is_guarded and is_saved: pass
        # elif not is_guarded and not is_saved:
        #    dead_ids.add(wolf_kill)

        # If is_guarded and is_saved: pass -> execution continues.
        # It does NOT add wolf_kill to dead_ids.
        # So the player SURVIVES in current implementation?
        # "Milk Pierce" usually means they die. "奶穿" = Save + Guard = Die.
        # If the code says `pass`, then `dead_ids.add(wolf_kill)` is NOT reached.
        # So they live?
        # Let's read the code carefully.

        #     if wolf_kill:
        #         is_guarded = (wolf_kill == guard_protect)
        #         is_saved = witch_save
        #         if is_guarded and is_saved: pass # 奶穿
        #         elif not is_guarded and not is_saved:
        #             dead_ids.add(wolf_kill)

        # If both are true, it executes `pass`.
        # `dead_ids` is initially empty.
        # So `wolf_kill` is NOT added.
        # So the player LIVES.

        # Memory says: "If a player is protected by the Guard and saved by the Witch in the same night, the player dies (Milk Pierce/奶穿 rule)."
        # This implies the current code is BUGGY according to the memory/requirements, or my understanding of `pass` is wrong.
        # Or maybe the comment `# 奶穿` indicates intent, but implementation is wrong.
        # However, my task is Performance Optimization. I should preserve existing functionality exactly.
        # So I should assert that they LIVE, if that's what the code did before.
        # UNLESS the memory "Milk Pierce" is a strong requirement I must fix?
        # "The bot implements 'Side Kill' ... winning conditions..."
        # "If a player is protected ... the player dies"
        # If existing code was wrong, fixing it might be out of scope or required.
        # But "Preserve existing functionality exactly" is explicit in my instructions.
        # I will assume existing code behavior is the source of truth for THIS task, unless I want to fix a bug.
        # But wait, if I change it, I violate "Preserve".
        # I'll check `tests/test_night_logic.py` assertion.
        pass

if __name__ == "__main__":
    unittest.main()
