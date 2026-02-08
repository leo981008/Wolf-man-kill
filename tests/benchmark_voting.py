
import asyncio
import time
import random
from unittest.mock import MagicMock, AsyncMock

# Mocking parts of the bot environment
class MockGame:
    def __init__(self, num_ai_players, history_size):
        self.lock = asyncio.Lock()
        self.game_active = True
        self.speaking_active = False
        self.ai_players = [MagicMock(name=f"AI_{i}", bot=True, mention=f"@AI_{i}") for i in range(num_ai_players)]
        for p in self.ai_players:
            p.name = f"AI_{p.name}"
        self.players = list(self.ai_players)
        self.voted_players = set()
        self.player_ids = {i: self.ai_players[i] for i in range(num_ai_players)}
        self.roles = {p: "平民" for p in self.ai_players}
        # Larger history entries
        self.speech_history = [f"Player {i%10}: Some speech content that takes up some space. " * 50 for i in range(history_size)]
        self.votes = {}

async def mock_get_ai_action(role, phase, targets, speech_history=None):
    return "0"

async def mock_send(msg):
    pass

async def perform_ai_voting_current(channel, game, ai_manager):
    ai_voters = []
    async with game.lock:
        if not game.game_active or game.speaking_active: return
        ai_voters = [p for p in game.ai_players if p in game.players and p not in game.voted_players]
        all_targets = list(game.player_ids.keys())

    if not ai_voters: return

    async def process_ai_voter(ai_player):
        role = "平民"
        current_history = []
        async with game.lock:
            role = game.roles.get(ai_player, "平民")
            current_history = list(game.speech_history)

        target_id = await ai_manager.get_ai_action(role, "白天投票階段", all_targets, speech_history=current_history)

        async with game.lock:
            game.voted_players.add(ai_player)

    tasks = [process_ai_voter(p) for p in ai_voters]
    await asyncio.gather(*tasks)

async def perform_ai_voting_optimized(channel, game, ai_manager):
    ai_voters = []
    shared_history = []
    ai_roles = {}
    async with game.lock:
        if not game.game_active or game.speaking_active: return
        ai_voters = [p for p in game.ai_players if p in game.players and p not in game.voted_players]
        all_targets = list(game.player_ids.keys())
        shared_history = list(game.speech_history)
        ai_roles = {p: game.roles.get(p, "平民") for p in ai_voters}

    if not ai_voters: return

    async def process_ai_voter(ai_player):
        role = ai_roles.get(ai_player, "平民")
        target_id = await ai_manager.get_ai_action(role, "白天投票階段", all_targets, speech_history=shared_history)

        async with game.lock:
            game.voted_players.add(ai_player)

    tasks = [process_ai_voter(p) for p in ai_voters]
    await asyncio.gather(*tasks)

async def benchmark():
    num_ai_players = 30
    history_size = 5000
    iterations = 50

    print(f"Benchmarking with {num_ai_players} AI players and {history_size} speech history entries.")

    # Warmup
    game = MockGame(10, 100)
    ai_manager = MagicMock()
    ai_manager.get_ai_action = AsyncMock(side_effect=mock_get_ai_action)
    channel = MagicMock()
    await perform_ai_voting_current(channel, game, ai_manager)
    await perform_ai_voting_optimized(channel, game, ai_manager)

    # Current
    start_time = time.time()
    for _ in range(iterations):
        game = MockGame(num_ai_players, history_size)
        ai_manager = MagicMock()
        ai_manager.get_ai_action = AsyncMock(side_effect=mock_get_ai_action)
        channel = MagicMock()
        await perform_ai_voting_current(channel, game, ai_manager)
    current_duration = time.time() - start_time
    print(f"Current implementation: {current_duration:.4f}s")

    # Optimized
    start_time = time.time()
    for _ in range(iterations):
        game = MockGame(num_ai_players, history_size)
        ai_manager = MagicMock()
        ai_manager.get_ai_action = AsyncMock(side_effect=mock_get_ai_action)
        channel = MagicMock()
        await perform_ai_voting_optimized(channel, game, ai_manager)
    optimized_duration = time.time() - start_time
    print(f"Optimized implementation: {optimized_duration:.4f}s")

    improvement = (current_duration - optimized_duration) / current_duration * 100
    print(f"Improvement: {improvement:.2f}%")

if __name__ == "__main__":
    asyncio.run(benchmark())
