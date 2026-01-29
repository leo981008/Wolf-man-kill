import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import bot

# Mock Discord Context
class MockContext:
    def __init__(self, author_id, guild_id):
        self.author = MagicMock()
        self.author.id = author_id
        self.author.name = f"User{author_id}"
        self.author.mention = f"<@{author_id}>"
        self.guild = MagicMock()
        self.guild.id = guild_id
        self.send = AsyncMock()
        self.channel = MagicMock()
        self.channel.set_permissions = AsyncMock()

@pytest.mark.asyncio
async def test_join_concurrency():
    # Reset game
    guild_id = 123
    game = bot.get_game(guild_id)
    game.reset()

    # Simulate 30 users joining concurrently
    users = [MockContext(i, guild_id) for i in range(30)]

    # Directly calling the callback function of the command
    tasks = [bot.join.callback(ctx) for ctx in users]
    await asyncio.gather(*tasks)

    print(f"Players joined: {len(game.players)}")
    assert len(game.players) <= 20
    assert len(game.players) == 20 # Should fill up to 20

@pytest.mark.asyncio
async def test_vote_input_validation():
    guild_id = 456
    game = bot.get_game(guild_id)
    game.reset()
    game.game_active = True

    p1 = MagicMock()
    p1.id = 1
    p1.name = "P1"
    game.players = [p1]
    game.player_ids = {1: p1}

    ctx = MockContext(1, guild_id)
    ctx.author = p1

    # Test long input
    long_str = "a" * 200
    await bot.vote.callback(ctx, target=long_str)

    # Verify "輸入過長" message
    args, _ = ctx.send.call_args
    assert "輸入過長" in args[0]

@pytest.mark.asyncio
async def test_die_permission_bypass():
    guild_id = 789
    game = bot.get_game(guild_id)
    game.reset()

    # Creator
    creator = MagicMock()
    creator.id = 1
    creator.guild_permissions.administrator = False

    # Random User
    user = MagicMock()
    user.id = 2
    user.guild_permissions.administrator = False

    # Admin
    admin = MagicMock()
    admin.id = 3
    admin.guild_permissions.administrator = True

    game.creator = creator

    # Case 1: Random user tries to use !die
    ctx = MockContext(2, guild_id)
    ctx.author = user
    await bot.die.callback(ctx, target="1")
    args, _ = ctx.send.call_args
    assert "權限不足" in args[0]

    # Case 2: Creator uses !die
    # Need to mock MemberConverter or setup players
    game.players = [user] # User 2 is target
    game.player_ids = {2: user}

    ctx = MockContext(1, guild_id)
    ctx.author = creator
    await bot.die.callback(ctx, target="2")

    # Should succeed (game.players empty after die?)
    assert user not in game.players
