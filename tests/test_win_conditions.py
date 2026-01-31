import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import bot

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.guild.id = 999
    ctx.send = AsyncMock()
    ctx.channel.set_permissions = AsyncMock()
    ctx.set_permissions = AsyncMock()
    ctx.guild.default_role = MagicMock()
    return ctx

@pytest.fixture
def reset_bot_state():
    bot.games = {}

@pytest.mark.asyncio
async def test_win_condition_wolves_win_slaughter_villagers(mock_ctx, reset_bot_state):
    """
    Test scenario: Wolves kill all Villagers (Side Kill).
    Expectation: Game should end (game_active = False).
    """
    game = bot.get_game(mock_ctx.guild.id)

    # Setup players
    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"
    p3 = MagicMock(name="Seer1") # God
    p3.name = "Seer1"

    game.players = [p1, p2, p3]
    game.roles = {
        p1: "狼人",
        p2: "平民",
        p3: "預言家"
    }
    game.game_active = True

    # Simulate Night: Wolf kills Villager (p2)
    dead_players = [p2]

    # Call perform_day with GAME object
    await bot.perform_day(mock_ctx, game, dead_players)

    assert game.game_active is False, "Game should end when all Villagers are dead"

@pytest.mark.asyncio
async def test_win_condition_wolves_win_slaughter_gods(mock_ctx, reset_bot_state):
    """
    Test scenario: Wolves kill all Gods (Side Kill).
    Expectation: Game should end.
    """
    game = bot.get_game(mock_ctx.guild.id)

    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"
    p3 = MagicMock(name="Seer1")
    p3.name = "Seer1"

    game.players = [p1, p2, p3]
    game.roles = {
        p1: "狼人",
        p2: "平民",
        p3: "預言家"
    }
    game.game_active = True

    # Simulate Night: Wolf kills Seer (p3)
    dead_players = [p3]

    await bot.perform_day(mock_ctx, game, dead_players)

    assert game.game_active is False, "Game should end when all Gods are dead"

@pytest.mark.asyncio
async def test_win_condition_good_wins(mock_ctx, reset_bot_state):
    """
    Test scenario: Good team votes out the last Wolf.
    Expectation: Game should end.
    """
    game = bot.get_game(mock_ctx.guild.id)

    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"

    game.players = [p1, p2]
    game.roles = {
        p1: "狼人",
        p2: "平民"
    }
    game.game_active = True
    game.votes = {p1: 2} # Both vote for wolf
    game.voted_players = {p1, p2}

    # Call resolve_votes with GAME object
    await bot.resolve_votes(mock_ctx, game)

    assert game.game_active is False, "Game should end when all Wolves are dead"
