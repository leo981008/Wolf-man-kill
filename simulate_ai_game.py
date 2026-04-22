import asyncio
from ai_manager import AIManager
from game_objects import GameState, PlayerList, AIPlayer
from dotenv import load_dotenv

async def simulate_werewolf_scenario():
    load_dotenv()
    print("狼人殺 AI (LiteLLM) 模擬測試展開...\n" + "-"*40)
    
    manager = AIManager()
    print(f"目前使用的 AI 提供者: {manager.provider}")
    
    # 建立一個簡單的遊戲狀態
    game = GameState()
    # 新增玩家
    ai_player_1 = AIPlayer("AI_狼人_1")
    ai_player_2 = AIPlayer("AI_預言家_2")
    user_player = AIPlayer("玩家_平民_3")
    
    game.players = PlayerList([ai_player_1, ai_player_2, user_player])
    game.roles = {
        ai_player_1: "狼人",
        ai_player_2: "預言家",
        user_player: "平民"
    }
    game.role_to_players = {
        "狼人": [ai_player_1],
        "預言家": [ai_player_2],
        "平民": [user_player]
    }
    game.alive_players = PlayerList(list(game.players))
    game.day = 1
    
    print("\n--- 模擬: 預言家夜晚查驗回合 ---")
    print(f"AI_預言家_2 正在思考要查驗誰...")
    try:
        # 呼叫 AI Manager 讓預言家取出選項
        action = await manager.get_ai_action(
            role="預言家",
            game_context="今天是第1天夜晚。你懷疑1號(狼人)和3號(平民)。你會查驗誰？",
            valid_targets=["1", "3"]
        )
        print(f"💡 AI_預言家_2 決定查驗: {action}")
    except Exception as e:
        print(f"預言家行動錯誤: {e}")

    print("\n--- 模擬: 白天發言階段 ---")
    print("昨日晚上平安夜，現在輪到 AI_狼人_1 發言...")
    try:
        # 提供對話上下文供 AI 發揮
        context = "當前局勢：今天是第1天的白天發言階段。昨晚平安夜。"
        speech = await manager.get_ai_speech(
            player_id=1,
            role="狼人",
            game_context=context
        )
        print(f"\n🐺 AI_狼人_1 發言:\n{speech}")
    except Exception as e:
        print(f"發言生成錯誤: {e}")

    finally:
        await manager.close()

if __name__ == "__main__":
    asyncio.run(simulate_werewolf_scenario())
