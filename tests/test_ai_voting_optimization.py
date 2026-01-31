import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import bot

@pytest.fixture
def mock_channel():
    channel = MagicMock()
    channel.send = AsyncMock()
    channel.guild.default_role = MagicMock()
    channel.set_permissions = AsyncMock()
    # Also need resolve_votes to work if called
    return channel

@pytest.mark.asyncio
async def test_perform_ai_voting_logic(mock_channel):
    # Setup game
    game = bot.GameState()
    game.game_active = True
    game.speaking_active = False # Must be False for voting

    # Create players
    p1 = bot.AIPlayer("AI1")
    p2 = bot.AIPlayer("AI2")
    p3 = bot.AIPlayer("AI3") # Dead
    p4 = bot.AIPlayer("AI4") # Already voted

    human = MagicMock()
    human.name = "Human"
    human.bot = False
    human.id = 12345
    # AIPlayer uses random ID, MagicMock needs explicit hash/eq support if put in set?
    # AIPlayer has __hash__. MagicMock hash depends on id(obj) by default.
    # But bot.py uses p.id for logic sometimes?
    # In voting: game.votes[target_member]

    # Setup game state
    # p3 is dead so not in game.players
    game.players = [p1, p2, p4, human]

    # ai_players tracks all AI players ever joined
    game.ai_players = [p1, p2, p3, p4]

    # voted_players tracks who has voted
    game.voted_players = {p4}

    game.player_ids = {
        101: p1, 102: p2, 103: p3, 104: p4, 105: human
    }

    # Patch resolve_votes to prevent it from running logic that might require more mocks
    # (though if everyone votes it calls resolve_votes)
    # logic: if len(game.voted_players) == len(game.players): should_resolve = True
    # Here: players=4. voted start=1. p1, p2 vote. Total=3.
    # If human doesn't vote, resolve_votes is NOT called.

    # Mock asyncio.sleep to be instant
    with patch('asyncio.sleep', new_callable=AsyncMock):
        # Mock ai_manager
        with patch('bot.ai_manager') as mock_ai_manager:
            # p1 votes for human (ID 105)
            # p2 abstains ("no")
            # p3 is dead (should not act)
            # p4 voted (should not act)
            mock_ai_manager.get_ai_action = AsyncMock(side_effect=["105", "no"])

            await bot.perform_ai_voting(mock_channel, game)

            # Check p1
            assert p1 in game.voted_players
            assert game.votes[human] == 1
            mock_channel.send.assert_any_call(f"{p1.mention} 投票給了 {human.mention}。")

            # Check p2
            assert p2 in game.voted_players
            mock_channel.send.assert_any_call(f"{p2.mention} 投了廢票。")

            # Check p3
            assert p3 not in game.voted_players

            # Check call count
            # Should be 2 calls: p1 and p2
            assert mock_ai_manager.get_ai_action.call_count == 2
