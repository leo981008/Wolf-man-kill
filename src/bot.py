import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

from src.game_models import GameState, Player, GamePhase
from src.game_engine import GameEngine
from src.ai_manager import AIManager
from src.utils import logger, safe_send

load_dotenv()

STANDARD_TEMPLATES = {
    6: {"狼人": 2, "預言家": 1, "女巫": 1, "獵人": 1, "平民": 1},
    7: {"狼人": 2, "預言家": 1, "女巫": 1, "獵人": 1, "平民": 2},
    8: {"狼人": 3, "預言家": 1, "女巫": 1, "獵人": 1, "平民": 2},
    9: {"狼人": 3, "預言家": 1, "女巫": 1, "獵人": 1, "平民": 3},
    10: {"狼人": 3, "預言家": 1, "女巫": 1, "獵人": 1, "守衛": 1, "平民": 3},
    12: {"狼人": 4, "預言家": 1, "女巫": 1, "獵人": 1, "守衛": 1, "平民": 4}
}




class WolfBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
        self.games = {}
        self.engines = {}
        self.ai = AIManager()

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Bot is ready and commands synced.")

bot = WolfBot()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    if channel_id in bot.games:
        game = bot.games[channel_id]
        if game.phase == GamePhase.DAY:
            player = next((p for p in game.players.values() if p.user.id == message.author.id), None)
            if player and player.is_alive:
                game.speech_history.append(f"{player.number}號: {message.content}")

    await bot.process_commands(message)

@bot.tree.command(name="join", description="加入或建立一場狼人殺遊戲")
async def join_game(interaction: discord.Interaction):
    channel_id = interaction.channel_id

    if channel_id not in bot.games:
        bot.games[channel_id] = GameState(interaction.channel, interaction.user)

    game = bot.games[channel_id]

    if game.phase != GamePhase.WAITING:
        await interaction.response.send_message("遊戲已經開始，無法加入。", ephemeral=True)
        return

    for p in game.players.values():
        if p.user.id == interaction.user.id:
            await interaction.response.send_message("你已經在遊戲中了！", ephemeral=True)
            return

    number = len(game.players) + 1
    player = Player(interaction.user, number)
    game.add_player(player)

    await interaction.response.send_message(f"{interaction.user.mention} 加入了遊戲！目前人數：{len(game.players)}")

@bot.tree.command(name="add_ai", description="加入一個 AI 玩家")
async def add_ai(interaction: discord.Interaction):
    channel_id = interaction.channel_id

    if channel_id not in bot.games:
        await interaction.response.send_message("目前沒有遊戲，請先使用 /join 建立遊戲。", ephemeral=True)
        return

    game = bot.games[channel_id]
    if game.phase != GamePhase.WAITING:
        await interaction.response.send_message("遊戲已經開始，無法加入。", ephemeral=True)
        return

    number = len(game.players) + 1

    class MockUser:
        def __init__(self, name, id):
            self.display_name = name
            self.name = name
            self.id = id
            self.mention = f"@{name}"
        async def send(self, *args, **kwargs):
            pass

    mock_user = MockUser(f"AI玩家{number}", number * -1)
    player = Player(mock_user, number, is_ai=True)
    game.add_player(player)

    await interaction.response.send_message(f"AI玩家{number} 加入了遊戲！目前人數：{len(game.players)}")

@bot.tree.command(name="start", description="開始遊戲")
async def start_game(interaction: discord.Interaction):
    channel_id = interaction.channel_id

    if channel_id not in bot.games:
        await interaction.response.send_message("目前沒有遊戲。", ephemeral=True)
        return

    game = bot.games[channel_id]

    if interaction.user.id != game.creator.id:
        await interaction.response.send_message("只有房主可以開始遊戲。", ephemeral=True)
        return

    player_count = len(game.players)
    if player_count < 6:
        await interaction.response.send_message("遊戲至少需要 6 名玩家。", ephemeral=True)
        return

    await interaction.response.defer()

    roles_dict = {}
    if player_count in STANDARD_TEMPLATES:
        roles_dict = STANDARD_TEMPLATES[player_count]
        await interaction.followup.send(f"使用標準 {player_count} 人板子。")
    else:
        await interaction.followup.send(f"玩家人數為 {player_count}，啟動「動態平衡板子生成」...")
        all_roles = ["狼人", "預言家", "女巫", "獵人", "守衛", "白痴", "平民"]
        dynamic_roles = await bot.ai.decide_roles_for_players(player_count, all_roles)

        if dynamic_roles:
            total_assigned = sum(dynamic_roles.values())
            roles_dict = dynamic_roles
            if total_assigned < player_count:
                roles_dict["旁觀天神"] = player_count - total_assigned

            roles_str = ", ".join([f"{k}: {v}" for k, v in roles_dict.items()])
            await safe_send(interaction.channel, f"AI 配置完成：{roles_str}")
        else:
            await safe_send(interaction.channel, "AI 配置失敗，遊戲取消。")
            del bot.games[channel_id]
            return

    engine = GameEngine(game, bot.ai)
    bot.engines[channel_id] = engine
    await engine.distribute_roles(roles_dict)
    await engine.start_night()

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token and token != "your_discord_token_here":
        bot.run(token)
    else:
        logger.error("Please set DISCORD_TOKEN in .env file.")
