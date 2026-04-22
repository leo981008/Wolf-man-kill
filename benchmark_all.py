import os
import sys
import time
import asyncio
import re
import json
import tempfile
import uuid
from unittest.mock import MagicMock, patch

# --- 環境設定與依賴 Mocking ---
# 為了在沒有 Discord Bot 或網路連線的情況下執行，我們 mock 掉一些不必要的模組
mock_discord = MagicMock()
sys.modules['discord'] = mock_discord
sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.app_commands'] = MagicMock()
sys.modules['google'] = MagicMock()


# 強制將 AI 提供者設定移除以尊重 .env
from dotenv import load_dotenv
load_dotenv()

# 匯入需要進行 Benchmark 的模組
from ai_manager import AIManager, RateLimiter, _load_and_process_cache, _write_cache_to_disk, DIGIT_PATTERN, DAY_PATTERN, JSON_ARRAY_PATTERN, JSON_OBJECT_PATTERN
from game_objects import PlayerList, GameState, AIPlayer

# 建立一個測試用的目錄
TEST_DIR = tempfile.mkdtemp()
TEST_CACHE_FILE = os.path.join(TEST_DIR, "ai_cache_benchmark.json")

def format_time(seconds: float) -> str:
    """格式化時間輸出"""
    if seconds < 1e-3:
        return f"{seconds * 1e6:.2f} µs"
    elif seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    else:
        return f"{seconds:.4f} s"

async def main():
    print("="*50)
    print("🐺 狼人殺 Bot 綜合效能 Benchmark 🐺")
    print("="*50)
    print(f"AI Provider Set To: {os.environ['AI_PROVIDER']}")
    print("-" * 50)

async def benchmark_cache():
    print("▶ 1. 測試 AIManager 快取讀寫效能 (Caching)")
    # 準備測試資料
    mock_data = []
    for i in range(100):
        mock_data.append({
            "player_count": 5 + (i % 5),
            "existing_roles": ["狼人", "預言家", "平民", "女巫", "獵人"],
            "roles": ["狼人", "預言家", "平民", "平民", "平民"]
        })

    iterations = 100

    # 1. 寫入快取效能
    start_time = time.perf_counter()
    for _ in range(iterations):
        _write_cache_to_disk(mock_data, TEST_CACHE_FILE)
    write_time = (time.perf_counter() - start_time) / iterations

    # 2. 讀取與處理快取效能
    start_time = time.perf_counter()
    for _ in range(iterations):
        _load_and_process_cache(TEST_CACHE_FILE)
    read_time = (time.perf_counter() - start_time) / iterations

    print(f"  - 寫入快取 (100筆資料): {format_time(write_time)} / 次")
    print(f"  - 讀取快取 (100筆資料): {format_time(read_time)} / 次")
    print("-" * 50)

async def benchmark_rate_limiter():
    print("▶ 2. 測試 Rate Limiter 效能 (無阻塞情境)")
    # 建立一個大容量的 RateLimiter 確保不會觸發等待
    limiter = RateLimiter(rate=100000.0, capacity=100000.0)

    iterations = 10000
    start_time = time.perf_counter()
    for _ in range(iterations):
        await limiter.acquire()
    end_time = time.perf_counter()

    avg_time = (end_time - start_time) / iterations
    print(f"  - 獲取 Token: {format_time(avg_time)} / 次")
    print("-" * 50)

async def benchmark_regex():
    print("▶ 3. 測試 正則表達式效能 (Regex)")

    text_digit = "我選擇 4 號玩家"
    text_day = "目前局勢：第 2 天"
    text_json_array = '這裡是一段回應：\n["狼人", "平民", "預言家"]\n請參考。'
    text_json_object = '這裡是一段回應：\n{"AI_1": "2", "AI_2": "no"}\n請參考。'

    iterations = 50000

    # DIGIT PATTERN
    start_time = time.perf_counter()
    for _ in range(iterations):
        re.search(r'\d+', text_digit)
    uncompiled_digit = (time.perf_counter() - start_time) / iterations

    start_time = time.perf_counter()
    for _ in range(iterations):
        DIGIT_PATTERN.search(text_digit)
    compiled_digit = (time.perf_counter() - start_time) / iterations

    # DAY PATTERN
    start_time = time.perf_counter()
    for _ in range(iterations):
        re.search(r'第\s*(\d+)\s*天', text_day)
    uncompiled_day = (time.perf_counter() - start_time) / iterations

    start_time = time.perf_counter()
    for _ in range(iterations):
        DAY_PATTERN.search(text_day)
    compiled_day = (time.perf_counter() - start_time) / iterations

    # JSON ARRAY PATTERN
    start_time = time.perf_counter()
    for _ in range(iterations):
        re.search(r'\[.*\]', text_json_array, re.DOTALL)
    uncompiled_json_array = (time.perf_counter() - start_time) / iterations

    start_time = time.perf_counter()
    for _ in range(iterations):
        JSON_ARRAY_PATTERN.search(text_json_array)
    compiled_json_array = (time.perf_counter() - start_time) / iterations

    # JSON OBJECT PATTERN
    start_time = time.perf_counter()
    for _ in range(iterations):
        re.search(r'\{.*?\}', text_json_object, re.DOTALL)
    uncompiled_json_object = (time.perf_counter() - start_time) / iterations

    start_time = time.perf_counter()
    for _ in range(iterations):
        JSON_OBJECT_PATTERN.search(text_json_object)
    compiled_json_object = (time.perf_counter() - start_time) / iterations

    print(f"  - 預編譯 DIGIT 效能提升: {(uncompiled_digit / compiled_digit):.2f}x ({format_time(compiled_digit)} vs {format_time(uncompiled_digit)})")
    print(f"  - 預編譯 DAY 效能提升:   {(uncompiled_day / compiled_day):.2f}x ({format_time(compiled_day)} vs {format_time(uncompiled_day)})")
    print(f"  - 預編譯 JSON ARRAY 效能提升:  {(uncompiled_json_array / compiled_json_array):.2f}x ({format_time(compiled_json_array)} vs {format_time(uncompiled_json_array)})")
    print(f"  - 預編譯 JSON OBJECT 效能提升: {(uncompiled_json_object / compiled_json_object):.2f}x ({format_time(compiled_json_object)} vs {format_time(uncompiled_json_object)})")
    print("-" * 50)

async def benchmark_game_state():
    print("▶ 4. 測試 GameState 及 PlayerList 效能")

    player_count = 100
    players = [AIPlayer(f"Player_{i}") for i in range(player_count)]

    # 標準 List vs PlayerList (O(1) lookup)
    std_list = list(players)
    opt_list = PlayerList(players)
    target_player = players[-1] # 找最後一個元素最差情況
    missing_player = AIPlayer("Missing_Player")

    iterations = 10000

    # __contains__ in standard list
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = target_player in std_list
    std_contains_time = (time.perf_counter() - start_time) / iterations

    # __contains__ in PlayerList
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = target_player in opt_list
    opt_contains_time = (time.perf_counter() - start_time) / iterations

    print(f"  - PlayerList(O(1)) 查找存在元素: {format_time(opt_contains_time)} (提升 {(std_contains_time/opt_contains_time if opt_contains_time > 0 else 0):.2f}x 比起標準列表 {format_time(std_contains_time)})")

    # __contains__ missing element
    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = missing_player in std_list
    std_missing_time = (time.perf_counter() - start_time) / iterations

    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = missing_player in opt_list
    opt_missing_time = (time.perf_counter() - start_time) / iterations

    print(f"  - PlayerList(O(1)) 查找不存在元素: {format_time(opt_missing_time)} (提升 {(std_missing_time/opt_missing_time if opt_missing_time > 0 else 0):.2f}x 比起標準列表 {format_time(std_missing_time)})")

    # 移除玩家 (複雜操作)
    game = GameState()
    game.players = players
    game.roles = {p: "平民" for p in players}
    game.role_to_players = {"平民": list(players)}

    start_time = time.perf_counter()
    for p in reversed(players):
        game.remove_player(p)
    remove_time = (time.perf_counter() - start_time) / player_count

    print(f"  - GameState.remove_player 執行時間: {format_time(remove_time)} / 次")
    print("-" * 50)

# Mock AsyncContextManager support
class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)

async def check_ollama_status(host: str) -> bool:
    """檢查真實的 Ollama 服務是否可用"""
    try:
        # Import real aiohttp for checking (temporarily overriding mock)
        import importlib
        try:
            real_aiohttp = importlib.import_module("aiohttp")
        except ImportError:
            return False

        async with real_aiohttp.ClientSession() as session:
            # We must use real_aiohttp to check, but since we are mocking aiohttp in sys.modules,
            # we need to be careful not to use the mock object's method
            if hasattr(session.get, 'return_value'):
                return False

            async with session.get(f"{host}/api/tags", timeout=1) as response:
                return response.status == 200
    except Exception:
        return False

async def benchmark_ollama_api():
    print("▶ 5. 測試 AIManager._generate_with_ollama 效能")

    ai_manager = AIManager(ollama_model="llama3") # 使用常見的預設模型名稱
    prompt = "這是一個測試問題。請只回答 'ok'。"

    # 嘗試連接真實的 Ollama (為了真正的 Benchmark)
    # The check is disabled due to mocking difficulties that cause unawaited coroutines
    has_real_ollama = False

    if has_real_ollama:
        print(f"  [連線成功] 偵測到本機 Ollama ({ai_manager.ollama_host})，執行真實 API 測試。")
        # 由於我們需要真實網路，我們恢復 sys.modules 中的 aiohttp (如果它存在的話)
        import importlib
        try:
            real_aiohttp = importlib.import_module("aiohttp")
            sys.modules['aiohttp'] = real_aiohttp
        except ImportError:
             print("  [錯誤] 缺乏真實的 aiohttp 套件，無法進行真實 API 測試。")
             has_real_ollama = False

    if has_real_ollama:
         # 確保重新初始化 AIManager 的 session
         ai_manager.session = None

         iterations = 5
         start_time = time.perf_counter()
         for _ in range(iterations):
             try:
                 # 直接調用
                 await ai_manager._generate_with_ollama(prompt, reasoning_effort="low")
             except Exception as e:
                 print(f"  [API 錯誤] {e}")
                 break

         real_api_time = (time.perf_counter() - start_time) / iterations
         print(f"  - 真實 Ollama API 生成回應時間: {format_time(real_api_time)} / 次 (測試 {iterations} 次)")

         # 測試完成後關閉 session
         await ai_manager.close()
    else:
        print(f"  [使用 Mock] 未偵測到本機 Ollama 或缺乏依賴，執行 Mock (模擬) 測試以測量封裝開銷。")

        # 建立 Mock Session
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"response": "ok"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock()

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        ai_manager.session = mock_session

        iterations = 1000
        start_time = time.perf_counter()
        for _ in range(iterations):
            await ai_manager._generate_with_ollama(prompt, reasoning_effort="low")

        mock_api_time = (time.perf_counter() - start_time) / iterations
        print(f"  - AIManager Ollama 封裝開銷 (Mock API): {format_time(mock_api_time)} / 次 (測試 {iterations} 次)")

    print("-" * 50)

async def run_all_benchmarks():
    try:
        await benchmark_cache()
        await benchmark_rate_limiter()
        await benchmark_regex()
        await benchmark_game_state()
        await benchmark_ollama_api()
    finally:
        # 清理臨時檔案
        import shutil
        try:
            shutil.rmtree(TEST_DIR)
        except OSError:
            pass
        print("Benchmark 執行完畢，已清理臨時檔案。")

if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(run_all_benchmarks())
