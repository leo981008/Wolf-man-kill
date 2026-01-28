import os
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# 遊戲板子配置 (從 Wiki 獲取)
GAME_TEMPLATES = {
    6: [
        {"name": "明牌局", "roles": ["狼人", "狼人", "預言家", "獵人", "平民", "平民"]},
        {"name": "暗牌局", "roles": ["狼人", "狼人", "預言家", "守衛", "平民", "平民"]}
    ],
    7: [
        {"name": "生還者", "roles": ["狼人", "白狼王", "預言家", "女巫", "獵人", "守衛", "平民"]}
    ],
    8: [
        {"name": "諸神黃昏", "roles": ["狼王", "白狼王", "惡靈騎士", "預言家", "女巫", "獵人", "守衛", "白痴"]},
        {"name": "末日狂徒", "roles": ["狼人", "狼人", "狼人", "預言家", "守衛", "騎士", "平民", "平民"]}
    ],
    9: [
        {"name": "暗牌局", "roles": ["狼人", "狼人", "狼人", "預言家", "女巫", "獵人", "平民", "平民", "平民"]}
    ],
    10: [
        {"name": "普通局", "roles": ["狼人", "狼人", "狼人", "預言家", "女巫", "獵人", "平民", "平民", "平民", "平民"]},
        {"name": "白痴局", "roles": ["狼人", "狼人", "狼人", "預言家", "女巫", "獵人", "白痴", "平民", "平民", "平民"]}
    ],
    12: [
        {"name": "預女獵白 標準板", "roles": ["狼人", "狼人", "狼人", "狼人", "預言家", "女巫", "獵人", "白痴", "平民", "平民", "平民", "平民"]},
        {"name": "狼王守衛", "roles": ["狼人", "狼人", "狼人", "狼王", "預言家", "女巫", "獵人", "守衛", "平民", "平民", "平民", "平民"]}
    ]
}

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

    if game_active:
        await ctx.send("遊戲已經在進行中。")
        return

    # 設定初始天神 (執行 !start 的人)
    gods = [ctx.author]

    # 如果天神在玩家列表中，將其移除
    if ctx.author in players:
        players.remove(ctx.author)
        await ctx.send(f"{ctx.author.mention} 已轉為天神 (God)，不參與遊戲。")

    current_player_count = len(players)
    if current_player_count < 3:
        await ctx.send("人數不足，至少需要 3 人 (不含天神) 才能開始。")
        return

    if current_player_count > 20:
        await ctx.send("人數過多，本遊戲最多支援 20 人。")
        return

    game_active = True
    roles = {}
    votes = {}
    voted_players = set()

    role_pool = []
    active_players = []
    template_name = ""

    # 判斷板子大小與選擇模板
    if current_player_count < 6:
        # 3-5 人：保留原有簡單邏輯
        werewolf_count = 1
        seer_count = 1
        villager_count = current_player_count - werewolf_count - seer_count

        role_pool = ["狼人"] * werewolf_count + ["預言家"] * seer_count + ["平民"] * villager_count
        template_name = f"{current_player_count}人 基礎局"
        active_players = players.copy()
    else:
        # 6人以上：使用 Wiki 板子
        # 找出最接近且不超過目前人數的板子大小
        supported_counts = sorted(GAME_TEMPLATES.keys(), reverse=True) # [12, 10, 9, 8, 7, 6]
        target_count = 0

        for count in supported_counts:
            if current_player_count >= count:
                target_count = count
                break

        # 處理多餘玩家 -> 轉為天神
        # 洗牌確保隨機選出 active players
        random.shuffle(players)

        active_players = players[:target_count]
        excess_players = players[target_count:]

        # 更新全域 players 列表，移除 excess players
        players[:] = active_players

        for p in excess_players:
            gods.append(p)
            await ctx.send(f"{p.mention} 因人數超出板子 ({target_count}人)，自動轉為天神。")

        # 隨機選擇板子
        templates = GAME_TEMPLATES[target_count]
        selected_template = random.choice(templates)
        role_pool = selected_template["roles"].copy()
        template_name = f"{target_count}人 {selected_template['name']}"

    # 分配身分
    random.shuffle(role_pool)

    role_summary = []
    for player, role in zip(active_players, role_pool):
        roles[player] = role
        role_summary.append(f"{player.name}: {role}")

        # 傳送身分給各個玩家
        try:
            await player.send(f"您的身分是：**{role}**")
        except discord.Forbidden:
            await ctx.send(f"無法發送私訊給 {player.mention}，請檢查隱私設定。")

    # 通知所有天神
    summary_msg = f"**本局板子：{template_name}**\n**本局身分列表：**\n" + "\n".join(role_summary)

    for god in gods:
        try:
            await god.send(summary_msg)
        except discord.Forbidden:
            await ctx.send(f"無法發送私訊給天神 {god.mention}。")

    await ctx.send(f"遊戲開始！使用板子：**{template_name}**。身分已發送給所有天神與玩家。")

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
