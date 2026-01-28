import os
import random
import asyncio
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

# 角色功能說明
ROLE_DESCRIPTIONS = {
    "狼人": "每晚可以與隊友討論並殺死一名玩家。目標是殺死所有神職或所有村民（屠邊）。",
    "預言家": "每晚可以查驗一名玩家的身分，知道他是好人還是狼人。",
    "平民": "沒有特殊技能，白天需根據發言投票找出狼人。",
    "獵人": "被狼人殺死或被投票出局時，可以開槍帶走一名玩家（被女巫毒死無法開槍）。",
    "守衛": "每晚可以守護一名玩家，防止其被狼人殺害。不能連續兩晚守護同一人。",
    "女巫": "擁有一瓶解藥和一瓶毒藥。解藥可救活被狼人殺害的玩家，毒藥可毒死一名玩家。兩瓶藥不能同一晚使用。",
    "白痴": "被投票出局時可以翻牌亮身分免死，但之後失去投票權，只能發言。",
    "狼王": "被殺死或投票出局時，可以發動技能帶走一名玩家（被毒死無法發動）。",
    "白狼王": "白天發言階段可以選擇自爆，並帶走一名場上存活的玩家。",
    "惡靈騎士": "擁有一次反傷技能。若被預言家查驗，預言家死亡；若被女巫毒殺，女巫死亡。",
    "騎士": "白天發言階段可以翻牌決鬥一名玩家。若該玩家是狼人，則狼人死亡；若為好人，則騎士死亡。",
    "隱狼": "被預言家查驗時顯示為好人。無狼刀，當其他狼人死光後獲得刀權（視板子規則而定）。",
    "老流氓": "平民陣營，被狼人殺害不會死，被女巫毒殺或獵人帶走會死。勝利條件與平民相同。",
}

# 設定 Intent (權限)
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 遊戲狀態
players = []
roles = {}
gods = []
votes = {}
voted_players = set()
game_active = False

# 新增：玩家編號與女巫藥水狀態
player_ids = {}     # ID -> Member
player_id_map = {}  # Member -> ID
witch_potions = {'antidote': True, 'poison': True}

def get_player_by_id(player_id):
    """根據 ID 獲取玩家物件"""
    try:
        pid = int(player_id)
        return player_ids.get(pid)
    except ValueError:
        return None

def get_id_by_player(player):
    """獲取玩家的 ID"""
    return player_id_map.get(player)

@bot.event
async def on_ready():
    print(f'{bot.user} 已上線！')

async def request_dm_input(player, prompt, valid_check, timeout=45):
    """私訊請求輸入的輔助函式"""
    try:
        await player.send(prompt)
        def check(m):
            return m.author == player and isinstance(m.channel, discord.DMChannel) and valid_check(m.content)

        msg = await bot.wait_for('message', check=check, timeout=timeout)
        return msg.content
    except (asyncio.TimeoutError, discord.Forbidden):
        return None

async def perform_night(ctx):
    """執行天黑邏輯 (循序發送私訊)"""
    # 1. 天黑禁言
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.send("🌑 **天黑請閉眼。** 夜晚行動開始，請留意私訊。")
    except discord.Forbidden:
        await ctx.send("權限不足，無法修改頻道權限。")

    # 驗證 ID 的輔助函式
    def is_valid_id(content):
        if content.strip().lower() == 'no': return True
        try:
            pid = int(content)
            return pid in player_ids
        except: return False

    # 2. 守衛階段
    guard_protect = None
    guard = next((p for p, r in roles.items() if r == "守衛" and p in players), None)
    if guard:
        resp = await request_dm_input(guard, "🛡️ **守衛請睜眼。** 今晚要守護誰？請輸入玩家編號 (輸入 no 空守):", is_valid_id)
        if resp and resp.lower() != 'no':
            guard_protect = int(resp)
            await guard.send(f"今晚守護了 {guard_protect} 號。")
        else:
            await guard.send("今晚不守護任何人。")

    # 3. 狼人階段 (多數決)
    wolf_kill = None
    wolves = [p for p, r in roles.items() if r == "狼人" and p in players]
    if wolves:
        # 發送請求給所有狼人
        tasks = []
        for wolf in wolves:
            tasks.append(request_dm_input(wolf, "🐺 **狼人請睜眼。** 今晚要殺誰？請輸入玩家編號 (輸入 no 放棄):", is_valid_id, timeout=60))

        # 等待所有狼人回應 (或超時)
        results = await asyncio.gather(*tasks)

        # 統計票數
        votes = []
        for res in results:
            if res and res.lower() != 'no':
                try: votes.append(int(res))
                except: pass

        if votes:
            from collections import Counter
            counts = Counter(votes)
            max_votes = counts.most_common(1)[0][1]
            candidates = [k for k, v in counts.items() if v == max_votes]
            wolf_kill = random.choice(candidates) # 平票隨機

            # 通知狼人目標
            for wolf in wolves:
                try: await wolf.send(f"今晚狼隊鎖定目標：**{wolf_kill} 號**。")
                except: pass
        else:
             for wolf in wolves:
                try: await wolf.send("今晚狼隊沒有達成目標 (或棄刀)。")
                except: pass

    # 4. 女巫階段
    witch_save = False
    witch_poison = None
    witch = next((p for p, r in roles.items() if r == "女巫" and p in players), None)
    if witch:
        # 解藥
        if witch_potions['antidote']:
            target_msg = f"今晚 {wolf_kill} 號玩家被殺了。" if wolf_kill else "今晚是平安夜。"
            prompt = f"🔮 **女巫請睜眼。** {target_msg} 要使用解藥嗎？(輸入 yes/no)"
            resp = await request_dm_input(witch, prompt, lambda c: c.strip().lower() in ['yes', 'y', 'no', 'n'])

            if resp and resp.strip().lower() in ['yes', 'y'] and wolf_kill:
                witch_save = True
                witch_potions['antidote'] = False
                await witch.send("已使用解藥。")
            else:
                await witch.send("未使用解藥。")
        else:
             # 解藥已用，僅通知資訊
             target_msg = f"今晚 {wolf_kill} 號玩家被殺了。" if wolf_kill else "今晚是平安夜。"
             await witch.send(f"🔮 **女巫請睜眼。** {target_msg} (解藥已用完)")

        # 毒藥
        if witch_potions['poison']:
            prompt = "要使用毒藥嗎？請輸入玩家編號 (輸入 no 不使用):"
            resp = await request_dm_input(witch, prompt, is_valid_id)
            if resp and resp.strip().lower() != 'no':
                witch_poison = int(resp)
                witch_potions['poison'] = False
                await witch.send(f"已對 {witch_poison} 號使用毒藥。")
            else:
                await witch.send("未使用毒藥。")

    # 5. 預言家階段
    seer = next((p for p, r in roles.items() if r == "預言家" and p in players), None)
    if seer:
        resp = await request_dm_input(seer, "🔮 **預言家請睜眼。** 今晚要查驗誰？請輸入玩家編號:", is_valid_id)
        if resp and resp.strip().lower() != 'no':
            target_id = int(resp)
            target_obj = player_ids.get(target_id)
            target_role = roles.get(target_obj, "未知") if target_obj else "未知"

            # 判斷好人/壞人 (隱狼算好人)
            is_bad = "狼" in target_role and target_role != "隱狼"
            result = "狼人 (查殺)" if is_bad else "好人 (金水)"

            await seer.send(f"{target_id} 號的身分是：**{result}**")
        else:
            await seer.send("今晚未查驗。")

    # 結算死亡名單
    dead_ids = set()

    # 狼刀
    if wolf_kill:
        is_guarded = (wolf_kill == guard_protect)
        is_saved = witch_save

        if is_guarded and is_saved:
            # 同守同救 -> 視為不死 (可根據規則調整)
            pass
        elif not is_guarded and not is_saved:
            dead_ids.add(wolf_kill)

    # 女巫毒
    if witch_poison:
        dead_ids.add(witch_poison)

    # 轉換為玩家物件
    dead_players_list = []
    for did in dead_ids:
        p = player_ids.get(did)
        if p and p in players:
            dead_players_list.append(p)

    await perform_day(ctx, dead_players_list)

async def perform_day(ctx, dead_players=[]):
    """執行天亮邏輯"""
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    except discord.Forbidden:
        await ctx.send("權限不足，無法修改頻道權限。請確認 Bot 擁有管理頻道權限。")

    msg = "🌞 **天亮了！** 請開始討論。\n"
    if dead_players:
        names = ", ".join([p.name for p in dead_players])
        msg += f"昨晚死亡的是：**{names}**"

        # 移除死亡玩家
        for p in dead_players:
            if p in players:
                players.remove(p)
    else:
        msg += "昨晚是平安夜。"

    await ctx.send(msg)

@bot.command()
async def join(ctx):
    """加入遊戲"""
    if game_active:
        await ctx.send("遊戲已經開始，無法加入。")
        return

    if ctx.author in gods:
        gods.remove(ctx.author)
        await ctx.send(f"{ctx.author.mention} 已從天神轉為玩家。")

    if ctx.author in players:
        await ctx.send(f"{ctx.author.mention} 你已經在玩家列表中了。")
    else:
        players.append(ctx.author)
        await ctx.send(f"{ctx.author.mention} 加入了遊戲！目前人數: {len(players)}")

@bot.command()
async def god(ctx):
    """轉為天神 (旁觀者)"""
    if ctx.author in players:
        players.remove(ctx.author)
        await ctx.send(f"{ctx.author.mention} 已從玩家轉為天神。")

    if ctx.author not in gods:
        gods.append(ctx.author)
        await ctx.send(f"{ctx.author.mention} 已加入天神組 (God)！")
    else:
        await ctx.send(f"{ctx.author.mention} 你已經是天神了。")

@bot.command()
async def start(ctx):
    """開始遊戲 (分配身分並進入天黑狀態)"""
    global game_active, roles, voted_players, votes, gods, player_ids, player_id_map, witch_potions

    if game_active:
        await ctx.send("遊戲已經在進行中。")
        return

    # 如果天神在玩家列表中，將其移除
    if ctx.author in players:
        players.remove(ctx.author)
        await ctx.send(f"{ctx.author.mention} 已轉為天神 (God)，不參與遊戲。")

    # 確保發起人是天神
    if ctx.author not in gods:
        gods.append(ctx.author)

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

    # 分配身分與編號
    random.shuffle(role_pool)

    # 分配編號 (1~N)
    player_ids = {}
    player_id_map = {}
    witch_potions = {'antidote': True, 'poison': True}

    player_list_msg = "**本局玩家列表：**\n"
    for idx, player in enumerate(active_players, 1):
        player_ids[idx] = player
        player_id_map[player] = idx
        player_list_msg += f"**{idx}.** {player.name}\n"

    await ctx.send(player_list_msg)

    role_summary = []
    for player, role in zip(active_players, role_pool):
        roles[player] = role
        pid = player_id_map[player]
        role_summary.append(f"{pid}. {player.name}: {role}")

        # 傳送身分給各個玩家
        try:
            description = ROLE_DESCRIPTIONS.get(role, "暫無說明")
            msg = f"您的編號是：**{pid}**\n您的身分是：**{role}**\n\n**功能說明：**\n{description}"
            await player.send(msg)
        except discord.Forbidden:
            await ctx.send(f"無法發送私訊給 {player.mention}，請檢查隱私設定。")

    # 通知所有天神
    summary_msg = f"**本局板子：{template_name}**\n**本局身分列表：**\n" + "\n".join(role_summary)

    for god in gods:
        try:
            await god.send(summary_msg)
        except discord.Forbidden:
            await ctx.send(f"無法發送私訊給天神 {god.mention}。")

    await ctx.send(f"遊戲開始！使用板子：**{template_name}**。身分與編號已發送給所有天神與玩家。")

    # 整理本局出現的角色功能說明
    unique_roles = set(role_pool)
    role_help_msg = "**本局角色功能說明：**\n"

    # 依照 ROLE_DESCRIPTIONS 定義的順序顯示，確保整齊
    for role in ROLE_DESCRIPTIONS:
        if role in unique_roles:
            role_help_msg += f"**{role}**：{ROLE_DESCRIPTIONS[role]}\n"

    # 如果有未知角色 (不在 ROLE_DESCRIPTIONS 中)，額外補上
    for role in unique_roles:
        if role not in ROLE_DESCRIPTIONS:
            role_help_msg += f"**{role}**：暫無說明\n"

    await ctx.send(role_help_msg)

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
async def die(ctx, *, target: str):
    """天神指令：處決玩家 (輸入編號)"""
    if ctx.author not in gods:
        await ctx.send("只有天神 (God) 可以使用此指令。")
        return

    # 嘗試解析玩家
    target_member = None

    # 1. 嘗試 ID
    if target.isdigit():
        target_member = player_ids.get(int(target))

    # 2. 嘗試 Mention / Name
    if not target_member:
        try:
            target_member = await commands.MemberConverter().convert(ctx, target)
        except commands.BadArgument:
            pass

    if not target_member:
        await ctx.send(f"找不到玩家 `{target}` (請輸入編號或名稱)。")
        return

    if target_member not in players:
        await ctx.send("該玩家不在遊戲中或已經死亡。")
        return

    # 執行處決
    players.remove(target_member)

    # 公告 (不公開身分)
    await ctx.send(f"👑 天神執行了處決，**{target_member.name}** 已死亡。")

    # 整理存活名單發送給所有天神
    living_status = "**目前存活玩家與身分：**\n"
    for p in players:
        r = roles.get(p, "未知")
        living_status += f"{p.name}: {r}\n"

    dead_player_role = roles.get(target_member, "未知")
    god_notification = f"💀 **{target_member.name}** ({dead_player_role}) 已死亡。\n{living_status}"

    for g in gods:
        try:
            await g.send(god_notification)
        except discord.Forbidden:
            pass

async def resolve_votes(ctx):
    """結算投票結果"""
    global players, votes, voted_players

    if not votes:
        # 所有人都投廢票
        await ctx.send("所有人均投廢票 (Abstain)，無人死亡。")
        # 重置投票狀態
        votes = {}
        voted_players = set()
        return

    # 計算票數
    max_votes = max(votes.values())
    candidates = [p for p, c in votes.items() if c == max_votes]

    if len(candidates) > 1:
        # 同票
        names = ", ".join([p.name for p in candidates])
        await ctx.send(f"平票！({names}) 均為 {max_votes} 票。請重新投票。")
        # 重置投票狀態
        votes = {}
        voted_players = set()
    else:
        # 有結果
        victim = candidates[0]
        await ctx.send(f"投票結束！**{victim.name}** 以 {max_votes} 票被處決。")

        # 移除玩家
        if victim in players:
            players.remove(victim)

        # 重置投票狀態 (等待下一輪)
        votes = {}
        voted_players = set()

@bot.command()
async def vote(ctx, *, target: str):
    """投票 [玩家] 或 [no] (廢票)"""
    if not game_active:
        await ctx.send("遊戲尚未開始。")
        return

    if ctx.author not in players:
        await ctx.send("你沒有參與這場遊戲。")
        return

    if ctx.author in voted_players:
        await ctx.send(f"{ctx.author.mention} 你已經投過票了！")
        return

    # 處理廢票
    if target.strip().lower() == "no":
        voted_players.add(ctx.author)
        await ctx.send(f"{ctx.author.mention} 投了廢票 (Abstain)。")
    else:
        # 嘗試解析玩家
        target_member = None

        # 1. 嘗試 ID
        if target.isdigit():
            target_member = player_ids.get(int(target))

        # 2. 嘗試 Mention / Name
        if not target_member:
            try:
                target_member = await commands.MemberConverter().convert(ctx, target)
            except commands.BadArgument:
                pass

        if not target_member:
            await ctx.send(f"找不到玩家 `{target}` (請輸入編號或名稱)。")
            return

        if target_member not in players:
            await ctx.send("該玩家不在遊戲中。")
            return

        # 記錄票數
        if target_member not in votes:
            votes[target_member] = 0

        votes[target_member] += 1
        voted_players.add(ctx.author)
        await ctx.send(f"{ctx.author.mention} 投票給了 {target_member.mention}！")

    # 檢查是否所有人都投完了
    if len(voted_players) == len(players):
        await resolve_votes(ctx)

@bot.command()
async def reset(ctx):
    """重置遊戲狀態"""
    global players, roles, votes, voted_players, game_active, gods, player_ids, player_id_map, witch_potions

    if game_active and ctx.author not in gods:
        await ctx.send("只有天神 (God) 才能在遊戲進行中重置遊戲。")
        return

    players = []
    roles = {}
    gods = []
    votes = {}
    voted_players = set()
    game_active = False

    # 重置新變數
    player_ids = {}
    player_id_map = {}
    witch_potions = {'antidote': True, 'poison': True}

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

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("錯誤: 未找到 DISCORD_TOKEN，請檢查 .env 檔案。")
