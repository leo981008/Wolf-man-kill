import os
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 設定 Intent (權限)
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 遊戲狀態
players = []
roles = {}
votes = {}
voted_players = set()
game_active = False

@bot.event
async def on_ready():
    print(f'{bot.user} 已上線！')

async def perform_night(ctx):
    """執行天黑邏輯"""
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🌑 **天黑請閉眼。** 頻道已禁言。")
    except discord.Forbidden:
        await ctx.send("權限不足，無法修改頻道權限。")

async def perform_day(ctx):
    """執行天亮邏輯"""
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.send("🌞 **天亮了！** 請開始討論。")
    except discord.Forbidden:
        await ctx.send("權限不足，無法修改頻道權限。請確認 Bot 擁有管理頻道權限。")

@bot.command()
async def join(ctx):
    """加入遊戲"""
    if game_active:
        await ctx.send("遊戲已經開始，無法加入。")
        return

    if ctx.author in players:
        await ctx.send(f"{ctx.author.mention} 你已經在玩家列表中了。")
    else:
        players.append(ctx.author)
        await ctx.send(f"{ctx.author.mention} 加入了遊戲！目前人數: {len(players)}")

@bot.command()
async def start(ctx):
    """開始遊戲 (分配身分並進入天黑狀態)"""
    global game_active, roles, voted_players, votes
    player_count = len(players)
    if player_count < 3:
        await ctx.send("人數不足，至少需要 3 人才能開始。")
        return

    if player_count > 20:
        await ctx.send("人數過多，本遊戲最多支援 20 人。")
        return

    if game_active:
        await ctx.send("遊戲已經在進行中。")
        return

    game_active = True
    roles = {}
    votes = {}
    voted_players = set()

    # 分配身分規則 (最多 20 人)
    # 3-5 人: 1 狼人
    # 6-9 人: 2 狼人
    # 10-14 人: 3 狼人
    # 15-20 人: 4 狼人
    if player_count <= 5:
        werewolf_count = 1
    elif player_count <= 9:
        werewolf_count = 2
    elif player_count <= 14:
        werewolf_count = 3
    else:
        werewolf_count = 4

    seer_count = 1
    villager_count = player_count - werewolf_count - seer_count

    role_pool = ["狼人"] * werewolf_count + ["預言家"] * seer_count + ["村民"] * villager_count
    random.shuffle(role_pool)

    role_summary = []
    for player, role in zip(players, role_pool):
        roles[player] = role
        role_summary.append(f"{player.name}: {role}")

    # 將所有身分發送給主持人 (執行 !start 的人)
    host = ctx.author
    try:
        summary_msg = "**本局身分列表：**\n" + "\n".join(role_summary)
        await host.send(summary_msg)
        await ctx.send(f"遊戲開始！身分已發送給主持人 {host.mention}。")
    except discord.Forbidden:
        await ctx.send(f"無法發送私訊給主持人 {host.mention}，請檢查隱私設定。遊戲無法開始。")
        game_active = False
        return

    # 進入天黑 (禁言)
    await perform_night(ctx)

@bot.command()
@commands.has_permissions(administrator=True)
async def day(ctx):
    """切換到天亮 (開啟發言權限，限管理員)"""
    await perform_day(ctx)

@bot.command()
@commands.has_permissions(administrator=True)
async def night(ctx):
    """切換到天黑 (關閉發言權限，限管理員)"""
    await perform_night(ctx)

@bot.command()
async def vote(ctx, target: discord.Member):
    """投票 [玩家]"""
    if not game_active:
        await ctx.send("遊戲尚未開始。")
        return

    if ctx.author not in players:
        await ctx.send("你沒有參與這場遊戲。")
        return

    if target not in players:
        await ctx.send("該玩家不在遊戲中。")
        return

    if ctx.author in voted_players:
        await ctx.send(f"{ctx.author.mention} 你已經投過票了！")
        return

    # 記錄票數
    if target not in votes:
        votes[target] = 0

    votes[target] += 1
    voted_players.add(ctx.author)

    await ctx.send(f"{ctx.author.mention} 投票給了 {target.mention}！目前 {target.name} 有 {votes[target]} 票。")

@bot.command()
async def reset(ctx):
    """重置遊戲狀態"""
    global players, roles, votes, voted_players, game_active
    players = []
    roles = {}
    votes = {}
    voted_players = set()
    game_active = False

    # 恢復發言權限
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    except:
        pass

    await ctx.send("遊戲已重置。")

# 錯誤處理
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("權限不足：此指令僅限管理員使用。")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("指令參數錯誤，請檢查用法。")
    else:
        print(f"Error: {error}")

if TOKEN:
    bot.run(TOKEN)
else:
    print("錯誤: 未找到 DISCORD_TOKEN，請檢查 .env 檔案。")
