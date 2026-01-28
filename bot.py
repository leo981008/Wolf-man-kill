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
    if len(players) < 3:
        await ctx.send("人數不足，至少需要 3 人才能開始。")
        return

    if game_active:
        await ctx.send("遊戲已經在進行中。")
        return

    game_active = True
    roles = {}
    votes = {}
    voted_players = set()

    # 分配身分 (簡易版: 1 狼人, 1 預言家, 其餘村民)
    role_pool = ["狼人", "預言家"] + ["村民"] * (len(players) - 2)
    random.shuffle(role_pool)

    for player, role in zip(players, role_pool):
        roles[player] = role
        try:
            await player.send(f"遊戲開始！你的身分是: **{role}**")
        except discord.Forbidden:
            await ctx.send(f"無法發送私訊給 {player.mention}，請檢查隱私設定。")

    await ctx.send("身分已發放！")

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
