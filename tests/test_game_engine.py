import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.game_engine import GameEngine
from src.game_models import GameState, Player, GamePhase, Werewolf, Witch, Guard, Seer, Faction
import unittest

class MockUser:
    def __init__(self, name="TestUser"):
        self.display_name = name

class MockChannel:
    def __init__(self):
        self.set_permissions = AsyncMock()
        self.send = AsyncMock()

class TestGameEngine(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_night_basic_kill(self):
        game = GameState(MockChannel(), MockUser())
        engine = GameEngine(game, MagicMock())

        p1 = Player(MockUser(), 1)
        p1.role = Werewolf()
        game.add_player(p1)

        p2 = Player(MockUser(), 2)
        p2.role = Witch()
        game.add_player(p2)

        game.phase = GamePhase.NIGHT
        game.day_count = 1

        engine.night_actions_cache[1] = 2 # Wolf kills 2
        await engine.resolve_night_phase1_and_start_witch()
        assert game.phase == GamePhase.NIGHT_WITCH_PHASE
        assert game.night_kills == [2]

        engine.night_actions_cache[2] = (0, 0) # Witch does nothing

        engine._end_game = AsyncMock()
        await engine.resolve_night_final()

        assert game.phase == GamePhase.DAY
        assert p2.is_alive == False
        assert p2.has_last_words == True

    async def test_resolve_night_witch_save(self):
        game = GameState(MockChannel(), MockUser())
        engine = GameEngine(game, MagicMock())

        p1 = Player(MockUser(), 1)
        p1.role = Werewolf()
        game.add_player(p1)

        p2 = Player(MockUser(), 2)
        p2.role = Witch()
        p2.is_ai = False # Test human witch flow via cache
        game.add_player(p2)

        game.phase = GamePhase.NIGHT
        game.day_count = 1

        engine.night_actions_cache[1] = 2 # Wolf kills 2
        await engine.resolve_night_phase1_and_start_witch()

        engine.night_actions_cache[2] = (2, 0) # Human Witch saves 2, poisons 0

        engine._end_game = AsyncMock()
        await engine.resolve_night_final()

        assert p2.is_alive == True

    async def test_resolve_night_seer_check(self):
        game = GameState(MockChannel(), MockUser())
        engine = GameEngine(game, MagicMock())

        p1 = Player(MockUser(), 1)
        p1.role = Werewolf()
        game.add_player(p1)

        p2 = Player(MockUser(), 2)
        p2.role = Seer()
        game.add_player(p2)

        game.phase = GamePhase.NIGHT
        game.day_count = 1

        engine.night_actions_cache[2] = 1 # Seer checks 1

        engine._end_game = AsyncMock()
        await engine.resolve_night_phase1_and_start_witch()

        # In a real test we'd intercept safe_send to check if the message contained "壞人"
        assert game.phase == GamePhase.NIGHT_WITCH_PHASE
