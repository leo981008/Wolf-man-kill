import os
import asyncio
import logging
import discord
from collections import deque
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from random import SystemRandom
from typing import Optional, List, Union, Callable
import io
from PIL import Image, ImageDraw, ImageFont
from functools import lru_cache

# Modules
from ai_manager import ai_manager
from game_data import (
    GAME_TEMPLATES, 
    ROLE_DESCRIPTIONS, 
    WOLF_FACTION, 
    GOD_FACTION, 
    VILLAGER_FACTION,
    SUPPORTED_COUNTS
)
from game_objects import (
    GameState, 
    AIPlayer, 
    get_game
)

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# 使用加密安全的隨機數產生器
secure_random = SystemRandom()

# 載入環境變數
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

@lru_cache(maxsize=1)
def _get_default_font():
    """快取並取得預設字體以提升效能"""
    try:
        return ImageFont.load_default(size=250)
    except Exception:
        return ImageFont.load_default()

@lru_cache(maxsize=20)
def _generate_number_image_bytes(number: int) -> bytes:
    """生成帶有編號的圖片位元組並快取"""
    # 建立一張 500x500 的黑色背景圖片
    img_size = 500
    image = Image.new("RGB", (img_size, img_size), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)

    text = str(number)

    # 取得快取的字體
    font = _get_default_font()

    # 計算文字位置並置中 (使用 textbbox)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (img_size - text_width) / 2
    y = (img_size - text_height) / 2

    # 微調 y 軸，因為 textbbox 的計算有時候不在視覺正中央
    draw.text((x, y - (bbox[1]/2)), text, fill=(255, 255, 255), font=font)

    # 將圖片存入記憶體
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()

def generate_number_image(number: int) -> io.BytesIO:
    """動態生成一張帶有編號的圖片（具備快取機制）"""
    image_bytes = _generate_number_image_bytes(number)
    return io.BytesIO(image_bytes)

# 設定 Intent (權限)
intents = discord.Intents.default()
intents.members = True # 需要讀取成員列表
intents.message_content = True # 需要讀取訊息內容

class WerewolfBot(commands.Bot):
    """
    自定義的 Discord Bot 類別。
    擴展了標準的 commands.Bot，用於管理 AI Manager 的生命週期。
    """
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        """
        Bot 啟動時的鉤子函式。
        用於初始化 AI 快取並同步 Slash Commands。
        """
        # 非同步初始化 AI Manager 快取
        await ai_manager.load_cache()

        # 注意: 全域同步可能需要一小時才能生效。開發時建議同步到特定 Guild。
        await self.tree.sync()
        logger.info("Slash commands synced globally.")

    async def close(self):
        """Bot 關閉時的清理工作。"""
        await ai_manager.close() # 確保關閉 aiohttp session
        await super().close()

bot = WerewolfBot()

def create_retry_callback(channel: discord.TextChannel) -> Callable:
    """
    建立一個 Callback 函式，用於在 AI 觸發速率限制重試時通知使用者。

    Args:
        channel: 訊息發送的目標頻道。
    Returns:
        一個無參數的 Coroutine function。
    """
    async def callback():
        try:
            await channel.send("⚠️ AI 正在思考中 (連線重試)... 請稍候。")
        except Exception:
            pass # 無法發送訊息時忽略 (例如權限不足或連線問題)
    return callback

@bot.event
async def on_ready():
    logger.info(f'{bot.user} 已上線！(Slash Commands Enabled)')

@bot.event
async def on_message(message: discord.Message):
    """
    全域訊息監聽器。
    主要用於記錄玩家在遊戲中的發言，作為 AI 的上下文。
    """
    if message.author.bot:
        return

    # 檢查是否為遊戲發言
    if message.guild:
        game = get_game(message.guild.id)
        if game.game_active:
            # 依序發言階段: 只有當前發言者被記錄
            if game.speaking_active:
                if game.current_speaker == message.author:
                     async with game.lock:
                         # 紀錄玩家發言格式: "Name: Content"
                         msg_content = f"{message.author.name}: {message.content}"
                         game.speech_history.append(msg_content)
            # 自由討論階段 (例如投票前): 所有存活玩家發言都被記錄
            elif message.author in game.players:
                 async with game.lock:
                     msg_content = f"{message.author.name}: {message.content}"
                     game.speech_history.append(msg_content)

    # 必須加上這行，否則 commands 框架會失效 (雖然本專案主要用 slash commands)
    await bot.process_commands(message)

async def announce_event(channel: discord.TextChannel, game: GameState, event_type: str, system_msg: str):
    """
    發送遊戲事件廣播，並附帶由 AI 生成的氛圍旁白。

    Args:
        channel: 目標頻道。
        game: 遊戲狀態物件。
        event_type: 事件類型 (用於生成旁白)。
        system_msg: 系統實際通知內容 (必定顯示)。
    """
    # 呼叫 AI 生成旁白
    narrative = await ai_manager.generate_narrative(event_type, system_msg, retry_callback=create_retry_callback(channel))

    if game.game_mode == "online":
        await channel.send(f"🎙️ **{narrative}**\n\n({system_msg})")
    else:
        # 線下模式: 嘗試私訊發送給主持人 (creator)，若失敗則直接發到頻道
        host_msg = f"🔔 **主持人提示** 🔔\n請宣讀以下內容：\n> {narrative}\n\n系統訊息：{system_msg}"
        sent = False
        if game.creator:
            try:
                await game.creator.send(host_msg)
                sent = True
            except Exception as e: 
                logger.warning(f"Failed to DM host: {e}")

        if not sent:
            await channel.send(f"*(無法私訊主持人，請直接宣讀)*\n{narrative}\n({system_msg})")
        else:
            await channel.send(f"*(已發送台詞給主持人 {game.creator.name})*")

async def announce_last_words(channel: discord.TextChannel, game: GameState, player: Union[discord.Member, AIPlayer], content: str):
    """
    公佈玩家遺言。

    同時將遺言加入 speech_history，讓其他 AI 玩家能「聽到」。
    """
    async with game.lock:
        game.speech_history.append(f"{player.name} (遺言): {content}")
    
    await channel.send(f"📢 **{player.name} 的遺言**：\n> {content}")

async def check_game_over(channel: discord.TextChannel, game: GameState):
    """
    檢查遊戲是否滿足獲勝條件。

    獲勝規則 (屠邊):
    1. 狼人獲勝: 神職全滅 OR 平民全滅。
    2. 好人獲勝: 狼人全滅。

    注意: 必須在 game.lock 保護下呼叫此函式，以確保數據一致性。
    """
    if not game.game_active:
        return

    wolf_count = game.wolf_count
    god_count = game.god_count
    villager_count = game.villager_count

    winner = None
    reason = ""

    # 狼人獲勝條件：屠邊
    if god_count == 0:
        winner = "狼人陣營"
        reason = "神職已全部陣亡 (屠邊)。"
    elif villager_count == 0:
        winner = "狼人陣營"
        reason = "平民已全部陣亡 (屠邊)。"

    # 好人獲勝條件：狼人全滅
    if wolf_count == 0:
        winner = "好人陣營"
        reason = "狼人已全部陣亡。"

    if winner:
        game.game_active = False
        await announce_event(channel, game, "遊戲結束", f"獲勝者：{winner}。原因：{reason}")

        # 公佈所有人的真實身分
        msg = "**本局玩家身分：**\n" + "".join(f"{p.name}: {r}\n" for p, r in game.roles.items())

        await channel.send(msg)

        try:
            # 嘗試恢復頻道發言權限
            await channel.set_permissions(channel.guild.default_role, send_messages=True)
        except (discord.Forbidden, discord.HTTPException) as e:
             logger.error(f"Failed to reset permissions: {e}")
             await channel.send("警告：Bot 權限不足，無法自動恢復頻道發言權限。")

        await channel.send("請使用 `/reset` 重置遊戲以開始新的一局。")

def is_valid_id(content: str, player_ids: dict) -> bool:
    """
    驗證輸入內容是否為有效的玩家 ID 或 'no'。
    """
    if content.strip().lower() == 'no': return True
    try:
        pid = int(content)
        return pid in player_ids
    except ValueError:
        return False

async def request_dm_input(player: Union[discord.Member, AIPlayer], prompt: str, valid_check: Callable[[str], bool], timeout: int = 45) -> Optional[str]:
    """
    私訊請求使用者輸入的通用輔助函式。

    Args:
        player: 目標玩家。
        prompt: 提示訊息。
        valid_check: 驗證輸入內容的函式 (回傳 True 表示有效)。
        timeout: 等待時間 (秒)。
    """
    try:
        await player.send(prompt)
        def check(m):
            try:
                # 確保是同一人、在私訊頻道、且內容符合格式
                if not (m.author == player and isinstance(m.channel, discord.DMChannel)):
                    return False
                if len(m.content) > 100:
                    return False
                return valid_check(m.content)
            except Exception:
                return False

        msg = await bot.wait_for('message', check=check, timeout=timeout)
        return msg.content
    except (asyncio.TimeoutError, discord.Forbidden):
        # 超時或被封鎖私訊
        return None
    except discord.HTTPException as e:
        logger.error(f"HTTP Exception in DM request: {e}")
        return None

async def perform_night(channel: discord.TextChannel, game: GameState):
    """
    執行「天黑」階段邏輯。

    流程：
    1. 設定頻道禁言。
    2. 並發 (Concurrent) 執行各個角色的夜晚行動 (狼人、女巫、預言家、守衛)。
    3. 結算夜晚結果 (死亡名單)。
    4. 切換到天亮階段。
    """
    try:
        # 檢查權限並設定頻道禁言
        perms = channel.permissions_for(channel.guild.default_role)
        if perms.send_messages:
            await channel.set_permissions(channel.guild.default_role, send_messages=False)

        await announce_event(channel, game, "天黑", "夜晚行動開始，請留意私訊。")
    except discord.Forbidden:
        await channel.send("警告：Bot 權限不足 (Manage Channels)，無法執行天黑禁言。")
    except discord.HTTPException as e:
        logger.error(f"Failed to set night permissions: {e}")
        await channel.send("錯誤：設定頻道權限時發生未知錯誤。")

    # 輸入驗證函式
    def is_valid_input(content):
        return is_valid_id(content, game.player_ids)

    # 統一獲取目標 ID 列表與歷史紀錄 (減少鎖的持有時間)
    async with game.lock:
        all_player_ids = [pid for pid, p in game.player_ids.items() if p in game.players]
        shared_history = list(game.speech_history)

    # 輔助：獲取行動 (自動判斷 AI 或真人)
    async def get_action(player, role, prompt, targets=None):
        if hasattr(player, 'bot') and player.bot:
            alive_count = len(game.players)
            return await ai_manager.get_ai_action(role, f"夜晚行動。場上存活 {alive_count} 人。", targets if targets else all_player_ids, speech_history=shared_history, retry_callback=create_retry_callback(channel))
        return await request_dm_input(player, prompt, is_valid_input)

    # --- 各角色邏輯 ---

    # 守衛
    async def run_guard():
        guard_protect = None
        async with game.lock:
            guard_candidates = game.role_to_players.get("守衛", [])
            guard = next((p for p in guard_candidates if p in game.players), None)

        if guard:
            resp = await get_action(guard, "守衛", "🛡️ **守衛請睜眼。** 今晚要守護誰？請輸入玩家編號 (輸入 no 空守):")
            if resp and resp.lower() != 'no':
                try:
                    guard_protect = int(resp)
                    try: await guard.send(f"今晚守護了 {guard_protect} 號。")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to guard: {e}")
                except ValueError: pass
            else:
                try: await guard.send("今晚不守護任何人。")
                except Exception as e:
                    logger.warning(f"Failed to send DM to guard: {e}")
        return guard_protect

    # 狼人
    async def run_wolf():
        async def safe_send(wolf, msg):
            try: await wolf.send(msg)
            except Exception as e:
                logger.warning(f"Failed to send DM to wolf {wolf.name}: {e}")

        wolf_kill = None
        async with game.lock:
            wolf_candidates = game.role_to_players.get("狼人", [])
            wolves = [p for p in wolf_candidates if p in game.players]

        if wolves:
            # 狼人分開詢問 (每個狼人單獨做決策，如果是 AI，會各自調用 LLM)
            tasks = []
            for wolf in wolves:
                prompt = "🐺 **狼人請睜眼。** 今晚要殺誰？請輸入玩家編號 (輸入 no 放棄):"
                tasks.append(get_action(wolf, "狼人", prompt))

            results = await asyncio.gather(*tasks)

            # 統計狼人投票
            votes = []
            for res in results:
                if res and res.lower() != 'no':
                    try:
                        votes.append(int(res))
                    except ValueError:
                        pass

            if votes:
                # 取最高票者為目標 (簡單多數決)
                max_votes = 0
                candidates = []
                counts = {}
                for target_id in votes:
                    count = counts.get(target_id, 0) + 1
                    counts[target_id] = count
                    if count > max_votes:
                        max_votes = count
                        candidates = [target_id]
                    elif count == max_votes:
                        candidates.append(target_id)
                wolf_kill = secure_random.choice(candidates)

                # 通知狼隊結果
                await asyncio.gather(*(safe_send(wolf, f"今晚狼隊鎖定目標：**{wolf_kill} 號**。") for wolf in wolves))
            else:
                await asyncio.gather(*(safe_send(wolf, "今晚狼隊沒有達成目標 (或棄刀)。") for wolf in wolves))
        return wolf_kill

    # 女巫 (依賴狼人結果，但因為 async 結構，我們先定義函式)
    async def run_witch(wolf_kill):
        witch_save = False
        witch_poison = None
        async with game.lock:
            witch_candidates = game.role_to_players.get("女巫", [])
            witch = next((p for p in witch_candidates if p in game.players), None)

        if witch:
            use_antidote = False
            async with game.lock:
                can_use_antidote = game.witch_potions['antidote']
                target_msg = f"今晚 {wolf_kill} 號玩家被殺了。" if wolf_kill else "今晚是平安夜。"

            # 解藥邏輯
            if can_use_antidote:
                prompt = f"🔮 **女巫請睜眼。** {target_msg} 要使用解藥嗎？(輸入 yes/no)"
                if hasattr(witch, 'bot') and witch.bot:
                    resp = "yes" if wolf_kill else "no" # AI 簡單邏輯：有人死就救 (這裡暫時簡化，未來可強化策略)
                else:
                    resp = await request_dm_input(witch, prompt, lambda c: c.strip().lower() in ['yes', 'y', 'no', 'n'])

                if resp and resp.strip().lower() in ['yes', 'y'] and wolf_kill:
                    witch_save = True
                    use_antidote = True
                    try: await witch.send("已使用解藥。")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to witch: {e}")
                else:
                    try: await witch.send("未使用解藥。")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to witch: {e}")
            else:
                 try: await witch.send(f"🔮 **女巫請睜眼。** {target_msg} (解藥已用完)")
                 except Exception as e:
                     logger.warning(f"Failed to send DM to witch: {e}")

            if use_antidote:
                 async with game.lock:
                    game.witch_potions['antidote'] = False

            # 毒藥邏輯
            use_poison = False
            poison_target_id = None
            async with game.lock:
                 can_use_poison = game.witch_potions['poison']

            if can_use_poison:
                resp = await get_action(witch, "女巫", "要使用毒藥嗎？請輸入玩家編號 (輸入 no 不使用):")
                if resp and resp.strip().lower() != 'no':
                    try:
                        witch_poison = int(resp)
                        use_poison = True
                        poison_target_id = witch_poison
                        try:
                            await witch.send(f"已對 {witch_poison} 號使用毒藥。")
                        except Exception as e:
                            logger.warning(f"Failed to send DM to witch: {e}")
                    except ValueError:
                        pass
                else:
                    try: await witch.send("未使用毒藥。")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to witch: {e}")

            if use_poison:
                 async with game.lock:
                    game.witch_potions['poison'] = False

        return witch_save, witch_poison

    # 預言家
    async def run_seer():
        async with game.lock:
            seer_candidates = game.role_to_players.get("預言家", [])
            seer = next((p for p in seer_candidates if p in game.players), None)

        if seer:
            resp = await get_action(seer, "預言家", "🔮 **預言家請睜眼。** 今晚要查驗誰？請輸入玩家編號:")
            if resp and resp.strip().lower() != 'no':
                try:
                    target_id = int(resp)
                    async with game.lock:
                        target_obj = game.player_ids.get(target_id)
                        target_role = game.roles.get(target_obj, "未知") if target_obj else "未知"

                    # 判定邏輯: 狼人陣營(不含隱狼)顯示為狼
                    is_bad = "狼" in target_role and target_role != "隱狼"
                    result = "狼人 (查殺)" if is_bad else "好人 (金水)"

                    try: await seer.send(f"{target_id} 號的身分是：**{result}**")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to seer: {e}")
                except ValueError:
                    try: await seer.send("無效的編號。")
                    except Exception as e:
                        logger.warning(f"Failed to send DM to seer: {e}")
            else:
                try: await seer.send("今晚未查驗。")
                except Exception as e:
                    logger.warning(f"Failed to send DM to seer: {e}")

    # --- 並發執行任務 ---

    # 建立任務
    guard_task = asyncio.create_task(run_guard())
    wolf_task = asyncio.create_task(run_wolf())
    seer_task = asyncio.create_task(run_seer())

    # 狼人必須先完成，女巫才能知道誰被殺
    wolf_kill = await wolf_task

    # 啟動女巫任務 (傳入狼刀結果)
    witch_task = asyncio.create_task(run_witch(wolf_kill))
    witch_save, witch_poison = await witch_task

    # 等待其他任務完成
    guard_protect = await guard_task
    await seer_task

    # --- 結算死亡 ---
    dead_ids = set()

    # 1. 狼刀結算 (考量守衛與女巫解藥)
    if wolf_kill:
        is_guarded = (wolf_kill == guard_protect)
        is_saved = witch_save

        # 同守同救 (奶穿) 規則：如果同時被守和被救，視為無效，玩家死亡
        if is_guarded and is_saved:
            dead_ids.add(wolf_kill)
        elif not is_guarded and not is_saved:
            dead_ids.add(wolf_kill)

    # 2. 女巫毒藥結算
    if witch_poison:
        dead_ids.add(witch_poison)

    dead_players_list = []
    async with game.lock:
        for did in dead_ids:
            p = game.player_ids.get(did)
            if p and p in game.players:
                dead_players_list.append(p)

    # 進入天亮階段
    await perform_day(channel, game, dead_players_list, poison_victim_id=witch_poison)

async def set_player_mute(member: Union[discord.Member, AIPlayer], mute: bool = True):
    """設定玩家靜音狀態的輔助函式。"""
    if not hasattr(member, 'voice') or not member.voice: return
    if member.voice.mute == mute: return
    try: await member.edit(mute=mute)
    except Exception as e:
        logger.warning(f"Failed to edit member {member.name}: {e}")

async def mute_all_players(channel: discord.TextChannel, game: GameState):
    """將所有玩家靜音。"""
    players_to_mute = []
    async with game.lock:
        players_to_mute = list(game.players)
    tasks = [set_player_mute(p, True) for p in players_to_mute]
    await asyncio.gather(*tasks)

async def unmute_all_players(channel: discord.TextChannel, game: GameState):
    """解除所有玩家靜音。"""
    players_to_unmute = []
    async with game.lock:
        players_to_unmute = list(game.players)
    tasks = [set_player_mute(p, False) for p in players_to_unmute]
    await asyncio.gather(*tasks)

async def perform_ai_voting(channel: discord.TextChannel, game: GameState):
    """
    執行 AI 玩家的投票邏輯。

    這是異步執行的，AI 玩家會模擬思考時間，然後進行投票。
    """
    await asyncio.sleep(5) # 模擬思考緩衝

    ai_voters = []
    shared_history = []
    ai_roles = {}
    async with game.lock:
        if not game.game_active or game.speaking_active: return
        # 篩選出還沒投票的存活 AI 玩家
        ai_voters = [p for p in game.ai_players if p in game.players and p not in game.voted_players]
        all_targets = [pid for pid, p in game.player_ids.items() if p in game.players]
        shared_history = list(game.speech_history)
        ai_roles = {p: game.roles.get(p, "平民") for p in ai_voters}

    if not ai_voters: return

    # 建立批量請求資料
    players_info = {str(p): ai_roles.get(p, "平民") for p in ai_voters}

    # 取得批量投票結果
    try:
        batch_results = await ai_manager.get_ai_action_batch(
            players_info,
            f"第 {game.day_count} 天白天投票階段。場上存活 {len(game.players)} 人。",
            all_targets,
            speech_history=shared_history,
            retry_callback=create_retry_callback(channel)
        )
    except Exception as e:
        logger.error(f"Error in batch AI voting: {e}")
        batch_results = {str(p): "no" for p in ai_voters}

    # 定義單個 AI 投票的處理邏輯
    async def process_ai_vote(ai_player):
        # 隨機延遲，模擬思考或分批輸出
        await asyncio.sleep(secure_random.uniform(0.5, 1.5))

        target_id = batch_results.get(str(ai_player), "no")
        target_member = None
        is_abstain = (str(target_id).strip().lower() == "no")
        if not is_abstain and str(target_id).isdigit():
            target_member = game.player_ids.get(int(target_id))

        async with game.lock:
            if ai_player in game.voted_players:
                return False

            if is_abstain:
                game.voted_players.add(ai_player)
                await channel.send(f"{ai_player.mention} 投了廢票。")
            else:
                if target_member and target_member in game.players:
                    if target_member not in game.votes:
                        game.votes[target_member] = 0
                    game.votes[target_member] += 1
                    game.voted_players.add(ai_player)
                    await channel.send(f"{ai_player.mention} 投票給了 {target_member.mention}。")
                else:
                    game.voted_players.add(ai_player)
                    await channel.send(f"{ai_player.mention} 投了廢票 (無效目標)。")

            # 檢查是否所有人都投票了
            if len(game.voted_players) == len(game.players):
                return True
        return False

    # 處理每一個 AI 的投票，並發執行
    tasks = [process_ai_vote(ai_player) for ai_player in ai_voters]
    results = await asyncio.gather(*tasks)

    # 只要有任何一個 AI 的投票觸發了 all-voted 條件
    if any(results):
        await resolve_votes(channel, game)

async def start_next_turn(channel: discord.TextChannel, game: GameState):
    """
    處理下一位玩家的發言回合。
    如果是 AI 玩家，則自動呼叫 AI 生成發言。
    """
    next_player = None
    remaining_count = 0

    async with game.lock:
        if not game.speaking_queue:
            # 佇列為空，檢查是否需要進行第二輪發言
            if game.speaking_round == 1:
                game.speaking_round = 2
                # 重新填充發言佇列 (過濾掉在第一輪死掉的玩家)
                game.speaking_queue = deque([p for p in game.speaking_order if p in game.players])
                game.speech_history.append("系統: --- 進入第二輪發言 ---")

                # 如果過濾後沒有存活玩家 (理論上不會，但防守一下)
                if not game.speaking_queue:
                    game.speaking_active = False
                    game.current_speaker = None
                    await channel.send("🎙️ **發言階段結束！** 現在可以自由討論與投票。")
                    asyncio.create_task(unmute_all_players(channel, game))
                    asyncio.create_task(perform_ai_voting(channel, game))
                    return
            else:
                # 佇列為空，且已經是第二輪，發言階段結束，進入自由討論/投票
                game.speaking_active = False
                game.current_speaker = None
                await channel.send("🎙️ **發言階段結束！** 現在可以自由討論與投票。")
                asyncio.create_task(unmute_all_players(channel, game))
                asyncio.create_task(perform_ai_voting(channel, game))
                return

        next_player = game.speaking_queue.popleft()
        game.current_speaker = next_player
        remaining_count = len(game.speaking_queue)

    # 解除當前發言者的靜音
    await set_player_mute(next_player, False)

    pid = "未知"
    role = "未知"
    async with game.lock:
        pid = game.player_id_map.get(next_player, "未知")
        role = game.roles.get(next_player, "平民")

    round_text = "第一輪" if game.speaking_round == 1 else "第二輪"
    await channel.send(f"🎙️ [{round_text}] 輪到 **{pid} 號 {next_player.mention}** 發言。 (剩餘 {remaining_count} 人等待)\n請發言完畢後輸入 `/done` 結束回合。")

    # 如果是 AI，自動發言
    if hasattr(next_player, 'bot') and next_player.bot:
        await asyncio.sleep(secure_random.uniform(0.1, 0.5))

        current_history = []
        day_count = 0
        dead_names = []
        round_num = 1
        async with game.lock:
            current_history = list(game.speech_history)
            day_count = game.day_count
            dead_names = list(game.last_dead_players)
            round_num = game.speaking_round

        alive_count = len(game.players)
        dead_info = ", ".join(dead_names) if dead_names else "無"
        context_str = f"現在是第 {day_count} 天白天。存活玩家: {alive_count} 人。昨晚死亡名單：{dead_info}。"

        # 呼叫 AI 生成發言
        speech = await ai_manager.get_ai_speech(pid, role, context_str, current_history, retry_callback=create_retry_callback(channel), round_num=round_num)

        async with game.lock:
            game.speech_history.append(f"{next_player.name}: {speech}")

        await channel.send(f"🗣️ **{next_player.name}**: {speech}")
        await asyncio.sleep(secure_random.uniform(0.5, 1.5)) # 閱讀緩衝

        await channel.send(f"*(AI {next_player.name} 發言結束)*")
        await set_player_mute(next_player, True)

        # 遞迴呼叫下一位
        await start_next_turn(channel, game)

async def handle_death_rattle(channel: discord.TextChannel, game: GameState, dead_players: List[Union[discord.Member, AIPlayer]], poison_victim_id: Optional[int] = None) -> List[Union[discord.Member, AIPlayer]]:
    """
    處理死亡玩家的「亡語」技能 (目前主要是獵人)。
    
    Returns:
        新增加的死亡玩家列表 (如被獵人帶走的玩家)。
    """
    new_dead_players = []
    processed_players = set()
    
    current_dead_batch = list(dead_players)
    
    # 循環處理，因為被帶走的人如果是獵人，也可能開槍 (雖然機率低，需看規則)
    while current_dead_batch:
        next_batch = []
        for player in current_dead_batch:
            if player in processed_players:
                continue
            processed_players.add(player)
            
            role = "未知"
            player_id = None
            async with game.lock:
                role = game.roles.get(player, "未知")
                player_id = game.player_id_map.get(player, None)

            # 獵人邏輯
            if role == "獵人":
                is_poisoned = (player_id == poison_victim_id)
                if is_poisoned:
                    await announce_event(channel, game, "獵人死亡", f"{player.mention} 試圖開槍，但發現槍管裡裝的是... 毒藥？(無法發動技能)")
                else:
                    await announce_event(channel, game, "獵人發動技能", f"{player.mention} 死亡時扣下了扳機！")
                    
                    target_id = None
                    if hasattr(player, 'bot') and player.bot:
                         # AI 獵人決策
                         alive_count = len(game.players)
                         async with game.lock:
                             shared_history = list(game.speech_history)
                             all_ids = [pid for pid, p in game.player_ids.items() if p in game.players]
                             
                         target_id = await ai_manager.get_ai_action("獵人", f"你已死亡。請選擇射擊目標。場上存活: {alive_count}", all_ids, speech_history=shared_history, retry_callback=create_retry_callback(channel))
                    else:
                        # 真人獵人決策
                        def is_valid(c):
                             if c.strip().lower() == 'no': return True
                             return c.isdigit() and int(c) in game.player_ids
                        
                        target_id = await request_dm_input(player, "🔫 **獵人請注意。** 你已死亡，請輸入想要射擊的玩家編號 (輸入 no 放棄):", is_valid)

                    if target_id and str(target_id).strip().lower() != 'no':
                        victim = None
                        async with game.lock:
                            victim = game.player_ids.get(int(target_id))
                            if victim and victim in game.players:
                                game.remove_player(victim) # 立即死亡
                                game.last_dead_players.append(victim.name)
                                
                        if victim:
                            await announce_event(channel, game, "獵人開槍", f"砰！**{victim.name}** 被帶走了。")
                            next_batch.append(victim)
                            new_dead_players.append(victim)
                    else:
                        await announce_event(channel, game, "獵人開槍", f"{player.mention} 選擇了不開槍。")

        current_dead_batch = next_batch
        
    return new_dead_players

async def perform_day(channel: discord.TextChannel, game: GameState, dead_players: Optional[List[Union[discord.Member, AIPlayer]]] = None, poison_victim_id: Optional[int] = None):
    """
    執行「天亮」階段邏輯。

    流程：
    1. 公佈死亡名單。
    2. 檢查遊戲是否結束。
    3. 處理亡語 (獵人)。
    4. 進入依序發言階段 (隨機排序)。
    """
    if dead_players is None:
        dead_players = []
    try:
        await channel.set_permissions(channel.guild.default_role, send_messages=True)
    except Exception as e:
        logger.error(f"Failed to set channel permissions: {e}")

    msg = "🌞 **天亮了！** 請開始討論。\n"
    game_over = False
    async with game.lock:
        game.day_count += 1
        game.last_dead_players = [p.name for p in dead_players]

        if dead_players:
            names = ", ".join(p.name for p in dead_players)
            msg += f"昨晚死亡的是：**{names}**"
            for p in dead_players:
                if p in game.players:
                    game.remove_player(p)
        else:
            msg += "昨晚是平安夜。"

        await check_game_over(channel, game)
        game_over = not game.game_active

    await announce_event(channel, game, "天亮", msg)

    # 處理亡語
    if dead_players:
         extra_dead = await handle_death_rattle(channel, game, dead_players, poison_victim_id)
         if extra_dead:
             # 有人被獵人帶走，需要再次檢查遊戲結束
             async with game.lock:
                 await check_game_over(channel, game)
                 game_over = not game.game_active

    if not game_over:
        await channel.send("🔊 **進入依序發言階段** (共兩輪討論)，正在隨機排序並設定靜音...")
        async with game.lock:
            temp_queue = list(game.players)
            secure_random.shuffle(temp_queue)
            game.speaking_order = list(temp_queue)
            game.speaking_queue = deque(temp_queue)
            game.speaking_round = 1
            game.speaking_active = True
            game.current_speaker = None
            game.speech_history = [] # 清空上一輪的發言紀錄

        await mute_all_players(channel, game)
        await start_next_turn(channel, game)

async def request_last_words(channel: discord.TextChannel, game: GameState, player: Union[discord.Member, AIPlayer]):
    """請求被處決玩家發表遺言。"""
    try:
        await channel.send(f"🎤 **請 {player.mention} 發表遺言。** (限時 60 秒)")
        
        content = None
        if hasattr(player, 'bot') and player.bot:
            # AI Logic
            async with game.lock:
                role = game.roles.get(player, "平民")
                shared_history = list(game.speech_history)
                msg = await ai_manager.get_ai_last_words(
                    player.name, 
                    role, 
                    f"現在是第 {game.day_count} 天，你被投票處決了。", 
                    speech_history=shared_history,
                    retry_callback=create_retry_callback(channel)
                )
                content = msg
        else:
            # Human Logic
            def check(m):
                return m.author == player and m.channel == channel and not m.author.bot
            
            try:
                msg = await bot.wait_for('message', check=check, timeout=60.0)
                content = msg.content
            except asyncio.TimeoutError:
                await channel.send("⏳ 時間到，未留下遺言。")
                return

        if content:
             await announce_last_words(channel, game, player, content)
            
    except Exception as e:
        logger.error(f"Error in request_last_words: {e}")
        await channel.send("(遺言環節發生錯誤，跳過)")

async def resolve_votes(channel: discord.TextChannel, game: GameState):
    """
    結算投票結果。

    1. 計算最高票。
    2. 處理平票 (重新投票)。
    3. 處決玩家。
    4. 處理亡語與遺言。
    """
    async with game.lock:
        if not game.votes:
            await channel.send("所有人均投廢票 (Abstain)，無人死亡。")
            game.votes = {}
            game.voted_players = set()
            return

        max_votes = -1
        candidates = []
        for p, c in game.votes.items():
            if c > max_votes:
                max_votes = c
                candidates = [p]
            elif c == max_votes:
                candidates.append(p)

    if len(candidates) > 1:
        # 平票處理
        names = ", ".join(p.name for p in candidates)
        msg = f"平票！({names}) 均為 {max_votes} 票。請重新投票。"
        await channel.send(msg)
        async with game.lock:
            game.speech_history.append(f"系統: {msg}")
            game.votes = {}
            game.voted_players = set()

        # 觸發新一輪 AI 投票
        asyncio.create_task(perform_ai_voting(channel, game))
    else:
        # 處決
        victim = candidates[0]
        await channel.send(f"投票結束！**{victim.name}** 以 {max_votes} 票被處決。")

        async with game.lock:
            if victim in game.players:
                game.remove_player(victim)
            game.votes = {}
            game.voted_players = set()
            await check_game_over(channel, game)
            
        # 遺言階段 (只有被投票出局且遊戲仍在進行時)
        if game.game_active:
             await request_last_words(channel, game, victim)

        # 亡語技能 (票出也能發動技能，不算毒死)
        if game.game_active:
             extra_dead = await handle_death_rattle(channel, game, [victim], poison_victim_id=None)
             if extra_dead:
                 async with game.lock:
                     await check_game_over(channel, game)

# --- Slash Commands ---

@bot.tree.command(name="join", description="加入遊戲")
async def join(interaction: discord.Interaction):
    """玩家加入遊戲的指令。"""
    game = get_game(interaction.guild_id)

    async with game.lock:
        if game.game_active:
            await interaction.response.send_message("遊戲已經開始，無法加入。", ephemeral=True)
            return

        # 如果原本是 God (觀戰)，轉為 Player
        if interaction.user in game.gods:
            game.gods.remove(interaction.user)
            await interaction.channel.send(f"{interaction.user.mention} 已從天神轉為玩家。")

        if interaction.user in game.players:
            await interaction.response.send_message("你已經在玩家列表中了。", ephemeral=True)
        else:
            if len(game.players) >= 20:
                await interaction.response.send_message("人數已達上限 (20人)。", ephemeral=True)
                return

            if not game.players and not game.gods:
                game.creator = interaction.user

            game.players.append(interaction.user)
            await interaction.response.send_message(f"{interaction.user.mention} 加入了遊戲！目前人數: {len(game.players)}")

@bot.tree.command(name="addbot", description="加入 AI 玩家")
async def addbot(interaction: discord.Interaction, count: int):
    """批量加入 AI 玩家的指令。"""
    game = get_game(interaction.guild_id)
    if game.game_active:
        await interaction.response.send_message("遊戲已開始，無法加入。", ephemeral=True)
        return

    if len(game.players) + count > 20:
        await interaction.response.send_message("人數將超過上限 (20)。", ephemeral=True)
        return

    added_names = []
    async with game.lock:
        for i in range(count):
            name = f"AI-{len(game.players)+1}"
            ai_p = AIPlayer(name)
            game.players.append(ai_p)
            game.ai_players.append(ai_p)
            added_names.append(name)

            if not game.creator:
                game.creator = interaction.user

    await interaction.response.send_message(f"已加入 {count} 名 AI 玩家: {', '.join(added_names)}")

@bot.tree.command(name="mode", description="設定遊戲模式")
@app_commands.choices(mode=[
    app_commands.Choice(name="線上模式 (AI主持)", value="online"),
    app_commands.Choice(name="線下模式 (AI場控)", value="offline")
])
async def mode(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    """切換遊戲模式 (線上/線下)。"""
    game = get_game(interaction.guild_id)
    async with game.lock:
        game.game_mode = mode.value

    desc = "AI 將負責主持遊戲並在頻道發送訊息。" if mode.value == "online" else "AI 將協助主持人，透過私訊發送流程提示。"
    await interaction.response.send_message(f"遊戲模式已設定為：**{mode.name}**\n{desc}")

@bot.tree.command(name="god", description="轉為天神 (旁觀者)")
async def god(interaction: discord.Interaction):
    """將自己設定為天神 (旁觀者/主持人)。"""
    game = get_game(interaction.guild_id)

    async with game.lock:
        if interaction.user in game.players:
            game.remove_player(interaction.user)
            await interaction.channel.send(f"{interaction.user.mention} 已從玩家轉為天神。")

        if interaction.user not in game.gods:
            if not game.players and not game.gods:
                game.creator = interaction.user
            game.gods.append(interaction.user)
            await interaction.response.send_message(f"{interaction.user.mention} 已加入天神組 (God)！")
        else:
            await interaction.response.send_message("你已經是天神了。", ephemeral=True)

@bot.tree.command(name="start", description="開始遊戲")
@app_commands.checks.cooldown(1, 10)
async def start(interaction: discord.Interaction):
    """開始遊戲的主要邏輯。"""
    game = get_game(interaction.guild_id)

    if game.game_active:
        await interaction.response.send_message("遊戲已經在進行中。", ephemeral=True)
        return

    await interaction.response.send_message("正在準備遊戲...")

    async with game.lock:
        # 重複檢查，避免 Race Condition
        if game.game_active:
            await interaction.followup.send("遊戲已經在進行中。")
            return

        game.creator = interaction.user
        if interaction.user not in game.players and interaction.user not in game.gods:
            game.gods.append(interaction.user)

        current_player_count = len(game.players)
        if current_player_count < 3:
            await interaction.followup.send("人數不足，至少需要 3 人 (不含天神) 才能開始。")
            return

        # 初始化遊戲狀態
        game.game_active = True
        game.roles = {}
        game.role_to_players = {}
        game.votes = {}
        game.voted_players = set()

        role_pool = []
        template_name = "未知"
        active_players = []

        # 選擇板子 (Template Selection)
        if current_player_count in GAME_TEMPLATES:
            # 標準人數，使用既定板子
            templates = GAME_TEMPLATES[current_player_count]
            selected_template = secure_random.choice(templates)
            role_pool = selected_template["roles"].copy()
            template_name = f"{current_player_count}人 {selected_template['name']}"
            active_players = game.players.copy()
        else:
            if current_player_count < 6:
                # 少人局基礎配置
                werewolf_count = 1
                seer_count = 1
                villager_count = current_player_count - werewolf_count - seer_count
                role_pool = ["狼人"] * werewolf_count + ["預言家"] * seer_count + ["平民"] * villager_count
                template_name = f"{current_player_count}人 基礎局"
                active_players = game.players.copy()
            else:
                # 嘗試 AI 生成板子
                await interaction.channel.send("⚠️ 偵測到非標準人數，正在請求 AI 生成平衡板子...")
                generated_roles = await ai_manager.generate_role_template(current_player_count, list(ROLE_DESCRIPTIONS.keys()), retry_callback=create_retry_callback(interaction.channel))

                if generated_roles:
                    role_pool = generated_roles
                    template_name = f"{current_player_count}人 AI 生成局"
                    active_players = game.players.copy()
                else:
                    # AI 失敗，回退到標準縮減邏輯
                    await interaction.channel.send("AI 生成失敗或連線逾時，切換為標準板子縮減模式。")
                    target_count = next((count for count in SUPPORTED_COUNTS if current_player_count >= count), 6)

                    secure_random.shuffle(game.players)
                    active_players = game.players[:target_count]
                    excess_players = game.players[target_count:]
                    game.players[:] = active_players

                    if excess_players:
                        game.gods.extend(excess_players)
                        mentions = " ".join(p.mention for p in excess_players)
                        await interaction.channel.send(f"{mentions} 因人數超出板子 ({target_count}人)，自動轉為天神。")

                    templates = GAME_TEMPLATES[target_count]
                    selected_template = secure_random.choice(templates)
                    role_pool = selected_template["roles"].copy()
                    template_name = f"{target_count}人 {selected_template['name']}"

        # 分配角色
        secure_random.shuffle(role_pool)
        game.player_ids = {}
        game.wolf_count = 0
        game.god_count = 0
        game.villager_count = 0
        game.player_id_map = {}
        game.witch_potions = {'antidote': True, 'poison': True}
        game.day_count = 0
        game.last_dead_players = []

        player_list_msg_lines = ["**本局玩家列表：**\n"]
        for idx, player in enumerate(active_players, 1):
            game.player_ids[idx] = player
            game.player_id_map[player] = idx
            player_list_msg_lines.append(f"**{idx}.** {player.name}\n")
        player_list_msg = "".join(player_list_msg_lines)

    await interaction.channel.send(player_list_msg)

    # 發送身分私訊
    role_summary = []
    for player, role in zip(active_players, role_pool):
        async with game.lock:
             game.roles[player] = role
             if role not in game.role_to_players:
                 game.role_to_players[role] = []
             game.role_to_players[role].append(player)

             if role in WOLF_FACTION:
                 game.wolf_count += 1
             elif role in GOD_FACTION:
                 game.god_count += 1
             elif role in VILLAGER_FACTION:
                 game.villager_count += 1

        pid = game.player_id_map[player]
        role_summary.append(f"{pid}. {player.name}: {role}")
        try:
            description = ROLE_DESCRIPTIONS.get(role, "暫無說明")
            msg = f"您的編號是：**{pid}**\n您的身分是：**{role}**\n\n**功能說明：**\n{description}"

            # 動態生成帶有編號的圖片
            image_buffer = generate_number_image(pid)
            discord_file = discord.File(fp=image_buffer, filename=f"number_{pid}.png")

            await player.send(msg, file=discord_file)
        except Exception as e:
            if not hasattr(player, 'bot') or not player.bot:
                logger.warning(f"Failed to DM {player.name}: {e}")
                await interaction.channel.send(f"無法發送私訊給 {player.mention}，請檢查隱私設定。")

    summary_msg = f"**本局板子：{template_name}**\n**本局身分列表：**\n" + "\n".join(role_summary)

    async def safe_send_summary(god, msg):
        try:
            await god.send(msg)
        except Exception as e:
            logger.warning(f"Failed to send summary DM to god {god.name}: {e}")

    if game.gods:
        await asyncio.gather(*(safe_send_summary(god, summary_msg) for god in game.gods))

    await announce_event(interaction.channel, game, "遊戲開始", f"使用板子：{template_name}")
    await interaction.channel.send("(資料來源: [狼人殺百科](https://lrs.fandom.com/zh/wiki/局式), CC-BY-SA)")

    # 開始第一夜
    await perform_night(interaction.channel, game)

@bot.tree.command(name="die", description="天神處決玩家")
async def die(interaction: discord.Interaction, target: str):
    """主持人強制處決玩家指令。"""
    game = get_game(interaction.guild_id)

    if not game.game_active:
        await interaction.response.send_message("遊戲尚未開始。", ephemeral=True)
        return

    is_admin = interaction.user.guild_permissions.administrator
    is_creator = (game.creator == interaction.user)

    if not (is_admin or is_creator):
        await interaction.response.send_message("權限不足。", ephemeral=True)
        return

    target_member = None
    if target.isdigit():
        target_member = game.player_ids.get(int(target))
    
    if not target_member:
        await interaction.response.send_message(f"找不到玩家 ID {target}", ephemeral=True)
        return

    async with game.lock:
        if target_member not in game.players:
            await interaction.response.send_message("該玩家不在遊戲中。", ephemeral=True)
            return
        game.remove_player(target_member)
        await check_game_over(interaction.channel, game)

    await interaction.response.send_message(f"👑 天神執行了處決，**{target_member.name}** 已死亡。")

@bot.tree.command(name="done", description="結束發言")
async def done(interaction: discord.Interaction):
    """玩家結束發言的指令。"""
    game = get_game(interaction.guild_id)

    is_speaking = False
    current_speaker = None
    async with game.lock:
        is_speaking = game.speaking_active
        current_speaker = game.current_speaker

    if not is_speaking:
        await interaction.response.send_message("現在不是發言階段。", ephemeral=True)
        return

    if interaction.user != current_speaker:
        is_admin = interaction.user.guild_permissions.administrator
        is_creator = (game.creator == interaction.user)
        if not (is_admin or is_creator):
             await interaction.response.send_message(f"現在是 {current_speaker.mention} 的發言時間。", ephemeral=True)
             return
        else:
             await interaction.channel.send(f"管理員/房主強制結束了 {current_speaker.name} 的發言。")

    await interaction.response.send_message("發言結束。")
    if current_speaker:
        await set_player_mute(current_speaker, True)
    await start_next_turn(interaction.channel, game)

@bot.tree.command(name="vote", description="投票")
async def vote(interaction: discord.Interaction, target_id: str):
    """玩家投票指令。"""
    # 輸入長度驗證 (防止濫用)
    if len(target_id) > 10:
        await interaction.response.send_message("輸入過長，請輸入有效的玩家編號。", ephemeral=True)
        return

    game = get_game(interaction.guild_id)

    if not game.game_active:
        await interaction.response.send_message("遊戲尚未開始。", ephemeral=True)
        return

    async with game.lock:
        if game.speaking_active:
            await interaction.response.send_message("請等待發言結束。", ephemeral=True)
            return

    if interaction.user not in game.players:
        await interaction.response.send_message("你沒有參與遊戲。", ephemeral=True)
        return

    is_abstain = (target_id.strip().lower() == "no")
    target_member = None
    if not is_abstain:
        if target_id.isdigit():
            target_member = game.player_ids.get(int(target_id))
        if not target_member:
             await interaction.response.send_message("無效的玩家編號。", ephemeral=True)
             return

    should_resolve = False
    async with game.lock:
        if interaction.user in game.voted_players:
            await interaction.response.send_message("你已經投過票了。", ephemeral=True)
            return

        if is_abstain:
            game.voted_players.add(interaction.user)
            await interaction.response.send_message(f"{interaction.user.mention} 投了廢票。")
        else:
            if target_member not in game.players:
                await interaction.response.send_message("該玩家不在遊戲中。", ephemeral=True)
                return
            if target_member not in game.votes:
                game.votes[target_member] = 0
            game.votes[target_member] += 1
            game.voted_players.add(interaction.user)
            await interaction.response.send_message(f"{interaction.user.mention} 投票成功。")

        if len(game.voted_players) == len(game.players):
            should_resolve = True

    if should_resolve:
        await resolve_votes(interaction.channel, game)

@bot.tree.command(name="reset", description="重置遊戲")
async def reset(interaction: discord.Interaction):
    """重置遊戲狀態 (限管理員)。"""
    game = get_game(interaction.guild_id)
    is_admin = interaction.user.guild_permissions.administrator
    is_creator = (game.creator == interaction.user)

    if not (is_admin or is_creator):
        await interaction.response.send_message("權限不足。", ephemeral=True)
        return

    async with game.lock:
        game.reset()

    try:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
    except Exception as e:
        logger.error(f"Failed to set channel permissions: {e}")

    await interaction.response.send_message("遊戲已重置。")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("錯誤: 未找到 DISCORD_TOKEN")
