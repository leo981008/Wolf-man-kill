import sys
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot

class TestTieVoting(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_votes_tie_triggers_ai_revote(self):
        # Setup mocks
        channel = MagicMock()
        channel.send = AsyncMock()

        game = bot.GameState()
        game.game_active = True

        # Create dummy players
        p1 = MagicMock()
        p1.name = "P1"
        p2 = MagicMock()
        p2.name = "P2"

        game.players = [p1, p2]

        # Simulate a tie
        game.votes = {p1: 1, p2: 1}
        game.voted_players = {p1, p2}

        # Patch perform_ai_voting to verify it gets called
        # Use AsyncMock, which when called returns an awaitable (coroutine-like)
        with patch('bot.perform_ai_voting', new_callable=AsyncMock) as mock_perform_ai_voting:

            # Call resolve_votes
            await bot.resolve_votes(channel, game)

            # Assert channel message about tie
            # We expect a message containing "平票" and "請重新投票"
            args, _ = channel.send.call_args
            msg = args[0]
            self.assertIn("平票", msg)
            self.assertIn("請重新投票", msg)

            # Assert votes are cleared
            self.assertEqual(game.votes, {})
            self.assertEqual(game.voted_players, set())

            # Assert perform_ai_voting was called
            mock_perform_ai_voting.assert_called_once_with(channel, game)

if __name__ == "__main__":
    unittest.main()
