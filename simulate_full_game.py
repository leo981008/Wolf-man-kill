# -*- coding: utf-8 -*-
import asyncio
import sys
from unittest.mock import MagicMock, AsyncMock, patch

# Force console to output utf-8 if supported
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Ensure the parent directory is in sys.path
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import bot
from game_objects import GameState, AIPlayer
from ai_manager import ai_manager

# 建立一個測試用的 Guild 和 Channel
class MockGuild:
    def __init__(self, id):
        self.id = id
        self.default_role = MagicMock()

class MockChannel:
    def __init__(self, name):
        self.name = name
        self.guild = MockGuild(12345)
    def permissions_for(self, role):
        mock_perms = MagicMock()
        mock_perms.send_messages = True
        return mock_perms
    async def send(self, msg, *args, **kwargs):
        # 移除 Discord Markdown Mentions 以便在控制台好讀
        clean_msg = str(msg).replace("<@interaction>", "HostUser")
        for i in range(1, 10):
            clean_msg = clean_msg.replace(f"<@{1000 + i}>", f"AI-{i}")
        print(f"[Channel] {clean_msg}")
        return MagicMock()
    async def set_permissions(self, *args, **kwargs):
        pass

class MockUser:
    def __init__(self, name, id, is_bot=False):
        self.name = name
        self.id = id
        self.mention = f"<@{id}>"
        self.bot = is_bot
        self.guild_permissions = MagicMock()
        self.guild_permissions.administrator = True
    async def send(self, msg, *args, **kwargs):
        # 簡化私訊輸出
        clean_msg = str(msg)
        for i in range(1, 10):
            clean_msg = clean_msg.replace(f"<@{1000 + i}>", f"AI-{i}")
        print(f"[DM to {self.name}] {clean_msg.split('\n')[0]} ...")
        return MagicMock()

class MockInteraction:
    def __init__(self, user, channel):
        self.user = user
        self.channel = channel
        self.guild = channel.guild
        self.guild_id = channel.guild.id
        self.response = MagicMock()
        self.response.send_message = AsyncMock(side_effect=self._send_response)
        self.followup = MagicMock()
        self.followup.send = AsyncMock(side_effect=self._send_followup)

    async def _send_response(self, msg, *args, **kwargs):
        print(f"[System Response to {self.user.name}] {msg}")
        
    async def _send_followup(self, msg, *args, **kwargs):
        print(f"[System Followup to {self.user.name}] {msg}")

# 模擬一場 6 人局遊戲
async def main():
    print("=" * 60)
    print("          狼人殺 Discord Bot 全自動遊戲流程模擬測試          ")
    print("=" * 60)

    # 1. 設置 Mock 環境
    channel = MockChannel("werewolf-game-channel")
    host = MockUser("HostUser", 1000)
    
    # 創建 6 個 AI 玩家
    ai_players = []
    for i in range(1, 7):
        p = AIPlayer(f"AI-{i}")
        p.id = 1000 + i
        p.mention = f"<@{1000 + i}>"
        # 讓 AI 玩家具有 send 方法以模擬私訊
        p.send = AsyncMock(side_effect=lambda msg, name=f"AI-{i}", **kwargs: print(f"[DM to {name}] {str(msg).replace(chr(10), ' ')}"))
        ai_players.append(p)
        
    # 設置 AI 行動與發言的 Mock 返回值
    mock_speech_map = {
        1: "我是個平民，昨晚平安夜，我覺得大家可以多交流，我暫時沒資訊。過。",
        2: "我是預言家！昨晚我查驗了 1 號，他的身份是：狼人 (查殺)！今天全票投給 1 號！",
        3: "我是女巫，昨晚 2 號被殺了我用了解藥救他，所以昨晚平安夜。今天我相信 2 號的查殺，出 1 號！",
        4: "我是守衛，昨晚我守護了 2 號預言家。既然 2 號有查殺，今天我也跟票 1 號。",
        5: "我是平民，今天票型很簡單，全票出 1 號狼人，沒問題的，過。",
        6: "我是平民（其實是狼人隊友）。我覺得 2 號發言太強勢了，可能 2 號才是悍跳狼吧？不過今天局勢不明朗，我先聽大家歸票。"
    }

    async def mock_get_ai_action(role, game_context, valid_targets, speech_history=None, retry_callback=None):
        # 根據角色做出合適的決定
        if role == "狼人":
            return "2"  # 殺 2 號預言家
        elif role == "預言家":
            return "1"  # 驗 1 號
        elif role == "女巫":
            return "no" # 不用毒藥
        elif role == "守衛":
            return "2"  # 守護 2 號
        elif role == "獵人":
            return "no"
        return "no"

    async def mock_get_ai_speech(player_id, role, game_context, speech_history=None, retry_callback=None, round_num=1):
        pid = int(player_id)
        return mock_speech_map.get(pid, "我是好人，過。")

    async def mock_get_ai_action_batch(players_info, game_context, valid_targets, speech_history=None, retry_callback=None):
        results = {}
        for name, role in players_info.items():
            if "AI-1" in name or "AI-6" in name:  # 狼人陣營
                results[name] = "2"  # 狼人垂死掙扎投預言家
            else:
                results[name] = "1"  # 好人全投 1 號狼人
        return results

    # 替換 AI Manager 的方法
    ai_manager.get_ai_action = mock_get_ai_action
    ai_manager.get_ai_speech = mock_get_ai_speech
    ai_manager.get_ai_action_batch = mock_get_ai_action_batch
    ai_manager.generate_narrative = AsyncMock(return_value="[AI Generated Narrative]")

    # 初始化遊戲
    game = bot.get_game(channel.guild.id)
    game.reset()
    
    # 設定為線上模式以輸出旁白
    game.game_mode = "online"
    
    # 2. 玩家加入
    print("\n--- [步驟 1] 玩家加入遊戲 ---")
    game.players = list(ai_players)
    game.ai_players = list(ai_players)
    print(f"成功加入 6 名 AI 玩家: {[p.name for p in game.players]}")
    
    # 3. 開始遊戲
    print("\n--- [步驟 2] 房主啟動遊戲 (/start) ---")
    start_interaction = MockInteraction(host, channel)
    
    # 角色順序：1狼人, 2預言家, 3女巫, 4守衛, 5平民, 6平民
    predefined_roles = ["狼人", "預言家", "女巫", "守衛", "平民", "平民"]
    
    real_shuffle = bot.secure_random.shuffle
    def smart_shuffle(x):
        if x and isinstance(x[0], str):
            x.clear()
            x.extend(predefined_roles)
        else:
            real_shuffle(x)
            
    with patch('bot.secure_random.shuffle', smart_shuffle):
        await bot.start.callback(start_interaction)
        
    print("\n--- [步驟 3] 檢查分配的角色 ---")
    for p, r in game.roles.items():
        print(f"User {p.name} 的真實身份為: {r} (遊戲編號: {game.player_id_map[p]} 號)")

    print(f"\n遊戲活躍狀態: {game.game_active}")
    print(f"平民存活: {game.villager_count} | 狼人存活: {game.wolf_count} | 神職存活: {game.god_count}")
    
    print("\n--- [步驟 4] 模擬等待全自動的夜晚與白天討論流轉 ---")
    print("（非同步任務正在背景執行：天黑禁言 -> 夜晚決策 -> 天亮公佈 -> 白天依序討論）")
    
    # 給予足夠時間讓背景的非同步依序討論和自動投票跑完
    # 6 個玩家討論大約需要 1~2 秒，但投票思考緩衝有 5 秒，因此需要足夠等待時間以供所有背景協程執行完畢
    await asyncio.sleep(15)
    
    print("\n--- [步驟 5] 結算投票與遊戲勝負結果 ---")
    print(f"投票結束後，遊戲活躍狀態: {game.game_active}")
    print(f"平民存活: {game.villager_count} | 狼人存活: {game.wolf_count} | 神職存活: {game.god_count}")
    
    # 驗證勝負
    if not game.game_active and game.wolf_count == 0:
        print("\n🎉【測試結果】好人陣營獲勝！1 號狼人被全票票出，遊戲順利結束並結算！")
    else:
        print("\n❌【測試結果】遊戲未按預期結束，請檢查邏輯。")

    print("\n--- [步驟 6] 測試重置遊戲 (/reset) ---")
    reset_interaction = MockInteraction(host, channel)
    await bot.reset.callback(reset_interaction)
    print(f"重置後遊戲活躍狀態: {game.game_active} (預期為 False)")
    print(f"重置後玩家人數: {len(game.players)} (預期為 0)")
    
    print("=" * 60)
    print("         狼人殺 Discord Bot 全自動端到端遊戲測試成功！         ")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
