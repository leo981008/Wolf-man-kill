import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
import bot

@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel.set_permissions = AsyncMock()
    ctx.guild.default_role = MagicMock()
    return ctx

@pytest.fixture
def reset_bot_state():
    bot.players = []
    bot.roles = []
    bot.game_active = False
    bot.gods = []
    bot.votes = {}
    bot.voted_players = set()
    bot.player_ids = {}
    bot.player_id_map = {}

@pytest.mark.asyncio
async def test_win_condition_wolves_win_slaughter_villagers(mock_ctx, reset_bot_state):
    """
    Test scenario: Wolves kill all Villagers (Side Kill).
    Expectation: Game should end (game_active = False).
    """
    # Setup players
    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"
    p3 = MagicMock(name="Seer1") # God
    p3.name = "Seer1"

    bot.players = [p1, p2, p3]
    bot.roles = {
        p1: "狼人",
        p2: "平民",
        p3: "預言家"
    }
    bot.game_active = True

    # Simulate Night: Wolf kills Villager (p2)
    dead_players = [p2]

    # Call perform_day (which currently just announces death)
    # We expect this to eventually contain the win check
    await bot.perform_day(mock_ctx, dead_players)

    assert bot.game_active is False, "Game should end when all Villagers are dead"
    # assert "狼人陣營獲勝" in mock_ctx.send.call_args_list[-1][0][0] # Optional check for message

@pytest.mark.asyncio
async def test_win_condition_wolves_win_slaughter_gods(mock_ctx, reset_bot_state):
    """
    Test scenario: Wolves kill all Gods (Side Kill).
    Expectation: Game should end.
    """
    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"
    p3 = MagicMock(name="Seer1")
    p3.name = "Seer1"

    bot.players = [p1, p2, p3]
    bot.roles = {
        p1: "狼人",
        p2: "平民",
        p3: "預言家"
    }
    bot.game_active = True

    # Simulate Night: Wolf kills Seer (p3)
    dead_players = [p3]

    await bot.perform_day(mock_ctx, dead_players)

    assert bot.game_active is False, "Game should end when all Gods are dead"

@pytest.mark.asyncio
async def test_win_condition_good_wins(mock_ctx, reset_bot_state):
    """
    Test scenario: Good team votes out the last Wolf.
    Expectation: Game should end.
    """
    p1 = MagicMock(name="Wolf1")
    p1.name = "Wolf1"
    p2 = MagicMock(name="Villager1")
    p2.name = "Villager1"

    bot.players = [p1, p2]
    bot.roles = {
        p1: "狼人",
        p2: "平民"
    }
    bot.game_active = True
    bot.votes = {p1: 2} # Both vote for wolf
    bot.voted_players = {p1, p2}

    # Call resolve_votes
    await bot.resolve_votes(mock_ctx)

    assert bot.game_active is False, "Game should end when all Wolves are dead"
