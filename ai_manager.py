import os
import inspect
import logging
import tempfile
from dotenv import load_dotenv
import asyncio
import json
import re
import aiohttp
import time
from collections import OrderedDict
from typing import Optional, List, Dict, Any, Union, Tuple, Callable

from ai_strategies import ROLE_STRATEGIES

logger = logging.getLogger(__name__)

# 最大回應長度（符合 Discord 訊息限制）
MAX_RESPONSE_LENGTH = 2000

load_dotenv()

# 預編譯正則表達式，提升重複使用的效能
DIGIT_PATTERN = re.compile(r'\d+')
DAY_PATTERN = re.compile(r'第\s*(\d+)\s*天')
JSON_ARRAY_PATTERN = re.compile(r'\[.*\]', re.DOTALL)
JSON_OBJECT_PATTERN = re.compile(r'\{.*?\}', re.DOTALL)

CALLBACK_TIMEOUT = aiohttp.ClientTimeout(total=120)

ALLOWED_URL_SCHEMES = ('http://', 'https://')

CACHE_FILE = "ai_cache.json"

def _load_and_process_cache(cache_file: str) -> Dict:
    """
    同步輔助函式：從磁碟載入並處理快取。

    此函式設計為在 Executor 中運行，避免阻塞主要 Event Loop。
    """
    if not os.path.exists(cache_file):
        return {}

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        result = {}
        for entry in data:
            # 驗證快取項目的完整性
            # 格式: {"player_count": 5, "existing_roles": [...], "roles": [...]}
            if not ("player_count" in entry and "existing_roles" in entry and "roles" in entry):
                continue

            player_count = entry["player_count"]
            existing_roles = tuple(entry["existing_roles"])
            roles = entry["roles"]

            # 使用 (人數, 可用角色tuple) 作為快取鍵
            key = (player_count, existing_roles)
            result[key] = roles
        return result
    except Exception as e:
        logger.error(f"Failed to load cache from disk: {e}")
        return {}


def _write_cache_to_disk(data: List[Dict], cache_file: str):
    """
    同步輔助函式：將快取寫入磁碟。

    此函式設計為在 Executor 中運行。
    使用「寫入臨時檔 -> 重新命名」的方式實現原子寫入，防止寫入中斷導致檔案損壞。
    """
    try:
        dir_name = os.path.dirname(os.path.abspath(cache_file))
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, cache_file)
        except Exception:
            # 發生錯誤時清理臨時檔
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.error(f"Failed to write cache to disk: {e}")
        raise

class RateLimitError(Exception):
    """當 API 速率限制被觸發時拋出的例外。"""
    pass

class RateLimiter:
    """
    使用權杖桶演算法 (Token Bucket Algorithm) 實現的速率限制器。

    用於控制對外部 API (如 Gemini) 的請求頻率，避免觸發 429 Too Many Requests 錯誤。
    """
    def __init__(self, rate: float, capacity: float):
        self.rate = rate  # 速率 (Tokens per second)
        self.capacity = capacity # 桶容量 (最大可用 Tokens)
        self.tokens = capacity # 當前可用 Tokens
        self.last_update = time.monotonic() # 上次更新時間
        self.lock = asyncio.Lock() # 確保線程安全

    async def acquire(self):
        """
        嘗試獲取一個 Token。如果沒有足夠的 Token，則非同步等待直到有 Token 可用。
        """
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update

            # 補充 Tokens
            self.tokens += elapsed * self.rate
            if self.tokens > self.capacity:
                self.tokens = self.capacity
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return

            # 計算需要等待的時間
            missing = 1 - self.tokens
            wait_time = missing / self.rate

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            # 等待結束後，Token 剛好補滿到 1 並被消耗掉，歸零
            self.tokens = 0
            self.last_update = time.monotonic()

class AIManager:
    """
    AI 管理器，負責處理所有與 LLM (Large Language Model) 的交互。

    功能包括：
    1. 支援多種 AI 提供者 (Ollama, Gemini API)。
    2. 管理 API 連線階段 (aiohttp session)。
    3. 實作重試機制與速率限制。
    4. 快取 AI 生成的結果 (如角色板子、旁白)。
    5. 建構 Prompt 並解析 AI 回應。
    """
    def __init__(self, ollama_model: Optional[str] = None):
        self.provider = os.getenv('AI_PROVIDER', 'gemini-api').lower()
        self.ollama_model = ollama_model or os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')
        self.ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')
        self.litellm_api_key = os.getenv('LITELLM_API_KEY')
        self.litellm_model = os.getenv('LITELLM_MODEL', 'gpt-3.5-turbo')
        self.litellm_base_url = os.getenv('LITELLM_BASE_URL', 'https://litellm.lianghsun.dev')
        self.session: Optional[aiohttp.ClientSession] = None

        logger.info(f"AI Manager initialized. Provider: {self.provider}")
        if self.provider == 'ollama':
            # 驗證 Ollama URL scheme 安全性
            if not any(self.ollama_host.startswith(scheme) for scheme in ALLOWED_URL_SCHEMES):
                logger.warning(f"Ollama host URL scheme not allowed: {self.ollama_host}. Resetting to default.")
                self.ollama_host = 'http://localhost:11434'
            logger.info(f"Ollama Model: {self.ollama_model}, Host: {self.ollama_host}")
        elif self.provider == 'gemini-api':
            logger.info(f"Gemini API Model: {self.gemini_model}")
        elif self.provider == 'litellm':
            logger.info(f"LiteLLM Model: {self.litellm_model}, Base URL: {self.litellm_base_url}")

        # Rate Limiter 設定: 15 RPM (每分鐘 15 次請求) = 0.25 requests/sec
        # Capacity 1 確保請求之間有嚴格的間隔
        self.rate_limiter = RateLimiter(rate=15/60.0, capacity=1.0)

        # 旁白快取 (LRU Cache)
        self.narrative_cache: OrderedDict = OrderedDict()

        # 角色板子快取
        self.role_template_cache: OrderedDict = OrderedDict()

        # 快取存檔鎖
        self.save_lock = asyncio.Lock()

    async def load_cache(self):
        """
        非同步載入快取。

        使用 run_in_executor 將檔案讀取操作移至線程池，避免阻塞 asyncio 事件循環。
        """
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, _load_and_process_cache, CACHE_FILE)
            if data:
                self.role_template_cache.update(data)
                logger.info(f"Loaded {len(self.role_template_cache)} entries from cache.")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")

    async def _save_cache(self):
        """
        非同步儲存快取。

        同樣使用 run_in_executor 將檔案寫入操作移至線程池。
        """
        async with self.save_lock:
            try:
                # 同步準備數據 (快速記憶體操作)
                data = []
                for (player_count, existing_roles), roles in self.role_template_cache.items():
                    data.append({
                        "player_count": player_count,
                        "existing_roles": list(existing_roles),
                        "roles": roles
                    })

                # 將阻塞的 I/O 操作交給 Executor
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, _write_cache_to_disk, data, CACHE_FILE)
            except Exception as e:
                logger.error(f"Failed to save cache: {e}")

    async def get_session(self) -> aiohttp.ClientSession:
        """
        獲取或創建 aiohttp ClientSession (Singleton 模式)。
        確保整個應用程式重用同一個連線池。
        """
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=CALLBACK_TIMEOUT)
        return self.session

    async def close(self):
        """關閉 AI Manager 及其連線階段。"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def _generate_with_ollama(self, prompt: str, reasoning_effort: str = "medium") -> str:
        """透過 Ollama API 生成回應。"""
        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False
        }
        # 設定思考程度 (low/medium/high) - 針對支援此參數的模型
        if reasoning_effort in ("low", "medium", "high"):
            payload["options"] = {"reasoning_effort": reasoning_effort}

        # 讓例外向上冒泡，由 generate_response 統一處理重試
        session = await self.get_session()
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("response", "").strip()
            else:
                error_text = await response.text()
                logger.error(f"Ollama API Error: {response.status} - {error_text}")
                # 如果是伺服器錯誤 (5xx)，拋出例外以觸發重試
                if response.status >= 500:
                    raise aiohttp.ClientError(f"Ollama Server Error: {response.status}")
                return ""

    async def _generate_with_litellm(self, prompt: str) -> str:
        """透過 LiteLLM (OpenAI compatible) API 生成回應。"""
        if not self.litellm_api_key:
            logger.error("LiteLLM API Key is missing.")
            return ""

        url = f"{self.litellm_base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.litellm_api_key}"
        }
        payload = {
            "model": self.litellm_model,
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            session = await self.get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    choices = data.get("choices", [])
                    if choices:
                        message = choices[0].get("message", {})
                        return message.get("content", "").strip()
                    return ""
                elif response.status == 429:
                    error_text = await response.text()
                    raise RateLimitError(f"LiteLLM 429: {error_text}")
                else:
                    error_text = await response.text()
                    logger.error(f"LiteLLM Error: {response.status} - {error_text}")
                    return ""
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"LiteLLM Connection Error: {e}")
            return ""

    async def _generate_with_gemini_api(self, prompt: str) -> str:
        """透過 Google Gemini REST API 生成回應。"""
        if not self.gemini_api_key:
            logger.error("Gemini API Key is missing.")
            return ""

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.gemini_api_key}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }

        try:
            session = await self.get_session()
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                    return ""
                elif response.status == 429:
                    error_text = await response.text()
                    raise RateLimitError(f"Gemini API 429: {error_text}")
                else:
                    error_text = await response.text()
                    logger.error(f"Gemini API Error: {response.status} - {error_text}")
                    return ""
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Gemini API Connection Error: {e}")
            return ""

    async def generate_response(self, prompt: str, retry_callback: Optional[Callable] = None, reasoning_effort: str = "medium") -> str:
        """
        生成回應的通用入口函式，包含速率限制與重試邏輯。

        Args:
            prompt: 給 AI 的提示詞。
            retry_callback: 當發生重試時呼叫的 Callback (通常用於通知使用者)。
            reasoning_effort: 思考程度 (low/medium/high)，目前主要用於 Ollama。
        """
        # 定義生成任務
        async def task():
            if self.provider == 'ollama':
                return await self._generate_with_ollama(prompt, reasoning_effort=reasoning_effort)
            elif self.provider == 'gemini-api' or self.provider == 'gemini':
                return await self._generate_with_gemini_api(prompt)
            elif self.provider == 'litellm':
                return await self._generate_with_litellm(prompt)
            else:
                logger.warning(f"Unknown provider: {self.provider}, defaulting to Gemini API")
                return await self._generate_with_gemini_api(prompt)

        # 重試與速率限制邏輯
        max_retries = 3
        base_delay = 4.0 # 基礎等待秒數 (指數退避)

        for attempt in range(max_retries + 1):
            try:
                # 主動速率限制 (針對 Gemini 和 LiteLLM)
                if 'gemini' in self.provider or self.provider == 'litellm':
                    await self.rate_limiter.acquire()

                return await task()

            except (RateLimitError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Connection/Rate limit error: {e}. Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")

                    if retry_callback:
                        try:
                            # 通知使用者正在重試
                            if inspect.iscoroutinefunction(retry_callback):
                                await retry_callback()
                            else:
                                retry_callback()
                        except Exception as cb_e:
                            logger.warning(f"Retry callback failed: {cb_e}")

                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Operation failed after {max_retries} retries: {e}")
                    return ""
            except Exception as e:
                logger.error(f"Unexpected error during generation: {e}", exc_info=True)
                return ""
        return ""

    def _truncate_response(self, text: str) -> str:
        """截斷過長的 AI 回應，確保符合 Discord 訊息長度限制 (2000字)。"""
        if len(text) > MAX_RESPONSE_LENGTH:
            return text[:MAX_RESPONSE_LENGTH - 3] + "..."
        return text

    async def generate_role_template(self, player_count: int, existing_roles: List[str], retry_callback: Optional[Callable] = None) -> List[str]:
        """
        生成平衡的角色板子。

        Args:
            player_count: 玩家總數。
            existing_roles: 可用的角色名稱列表。
        Returns:
            List[str]: 生成的角色列表 (e.g., ["狼人", "預言家", "平民"])。
        """
        # 建立快取鍵
        cache_key = (player_count, tuple(sorted(existing_roles)))

        # 檢查快取
        if cache_key in self.role_template_cache:
            self.role_template_cache.move_to_end(cache_key) # 更新 LRU
            return self.role_template_cache[cache_key]

        prompt = f"""
        請為 {player_count} 名玩家設計一個平衡的狼人殺配置。
        只能使用以下角色：{', '.join(existing_roles)}。
        必須包含至少一名狼人。
        請只回傳一個 JSON 格式的字串列表，例如：["狼人", "預言家", "平民"]。
        不要包含 markdown 標記或其他文字。

        重要規則：
        - 陣列長度必須恰好等於 {player_count}。
        - 只能使用上述列出的角色名稱，不可發明新角色。
        - 回傳內容必須是純 JSON 陣列，不可包含任何解釋、說明或其他文字。
        """

        response_text = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="low")
        try:
            # 嘗試提取 JSON 陣列部分
            match = JSON_ARRAY_PATTERN.search(response_text)
            clean_text = match.group(0) if match else response_text

            roles = json.loads(clean_text)
            if isinstance(roles, list) and len(roles) == player_count:
                # 驗證所有角色是否合法
                existing_roles_set = set(existing_roles)
                if existing_roles_set.issuperset(roles):
                    # 寫入快取
                    self.role_template_cache[cache_key] = roles
                    # 維持快取大小限制
                    if len(self.role_template_cache) > 100:
                        self.role_template_cache.popitem(last=False)
                    await self._save_cache()
                    return roles
            if response_text:
                logger.warning(f"Invalid generated roles for {player_count} players: {roles}")
            return []
        except Exception as e:
            logger.error(f"Role generation failed: {e}\nResponse: {response_text}")
            return []

    async def generate_narrative(self, event_type: str, context: str, language: str = "zh-TW", retry_callback: Optional[Callable] = None) -> str:
        """
        生成遊戲事件的旁白 (Flavor Text)。

        Args:
            event_type: 事件類型 (如 "天黑", "天亮", "死亡")。
            context: 事件詳細描述 (如 "平安夜", "3號玩家死亡")。
        """
        # 使用 context 字串作為快取鍵，確保可雜湊
        cache_key = (event_type, str(context), language)
        if cache_key in self.narrative_cache:
            self.narrative_cache.move_to_end(cache_key)
            return self.narrative_cache[cache_key]

        prompt = f"""
        你是一個狼人殺遊戲的主持人（上帝）。
        請根據以下情境，生成一段富有氛圍的旁白（約 30-50 字）。
        請直接輸出旁白內容，不要加上「主持人：」等前綴。

        氛圍指導：
        - 天黑事件：使用懸疑、恐怖的語調，營造緊張氣氛。
        - 天亮事件：如果有死亡，語調沉重悲傷；如果平安夜，語調輕鬆帶有警覺。
        - 遊戲結束：使用史詩、壯烈的語調。
        - 每次旁白要有變化，避免重複相同的句式。

        ⚠️ 嚴格限制：
        - 你只能根據下方提供的事件資訊生成旁白。
        - 嚴禁透露任何玩家的身分、角色、或未公開的遊戲資訊。
        - 嚴禁編造未發生的事件或添加下方未提及的細節。
        - 只描述氛圍和情境，不要加入具體的遊戲判斷。

        事件類型：{event_type}
        詳細資訊：{context}
        """
        response = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="low")

        if response:
            response = self._truncate_response(response)
            self.narrative_cache[cache_key] = response
            if len(self.narrative_cache) > 100:
                self.narrative_cache.popitem(last=False)

        return response

    async def get_ai_action(self, role: str, game_context: str, valid_targets: List[str], speech_history: Optional[List[str]] = None, retry_callback: Optional[Callable] = None) -> str:
        """
        決策 AI 玩家的行動 (如夜晚殺人、白天投票)。

        Args:
            role: AI 的角色。
            game_context: 當前局勢描述。
            valid_targets: 合法的目標 ID 列表。
            speech_history: 相關的發言歷史 (用於判斷投票邏輯)。
        Returns:
            str: 目標 ID 或 'no' (放棄)。
        """
        strategy_info = ROLE_STRATEGIES.get(role, {})
        action_guide = strategy_info.get("action_guide", "")
        voting_guide = strategy_info.get("voting_guide", "")
        reasoning_guide = strategy_info.get("reasoning_guide", "")

        history_text = ""
        if speech_history:
            history_text = "\n本輪發言/討論紀錄：\n" + "\n".join(speech_history)

        # 判斷是投票階段還是夜晚行動
        is_voting = "投票" in game_context
        phase_guide = voting_guide if is_voting else action_guide
        phase_label = "投票決策" if is_voting else "夜晚行動決策"

        prompt = f"""
# {phase_label}
你正在玩狼人殺。你的身分是：【{role}】。
當前局勢：{game_context}
你可以選擇的目標（玩家編號）有：{valid_targets}。
{history_text}

# 決策分析（僅供內部推理，不要輸出分析過程）
請在心中完成以下分析步驟，然後只輸出最終的目標編號：
{reasoning_guide}

# 策略指導
{phase_guide}

⚠️ 行動規則（必須遵守）：
- 你「只能」從上方列出的「可選擇目標」中選擇一個編號。
- 不要選擇不在目標列表中的編號。
- 你只能依據上方提供的「當前局勢」和「發言紀錄」做出判斷，不可虛構理由。
- 如果資訊不足以做出判斷，請回傳 'no'。

# 輸出格式
請只回傳你選擇的目標編號（一個數字）。
如果你決定不行動、空守或棄票，請回傳 'no'。
只回傳結果，不要解釋。
"""
        response = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="high")
        clean = response.strip().lower().replace(".", "")

        if "no" in clean:
            return "no"

        match = DIGIT_PATTERN.search(clean)
        if match:
            target_val = match.group()
            if valid_targets:
                valid_set = {str(t) for t in valid_targets}
                if target_val in valid_set:
                    return target_val
                else:
                    logger.warning(f"AI returned invalid target {target_val} (not in {valid_targets}) for role {role}. Falling back to 'no'.")
                    return "no"
            return target_val
        return "no"


    async def get_ai_action_batch(self, players_info: Dict[str, str], game_context: str, valid_targets: List[str], speech_history: Optional[List[str]] = None, retry_callback: Optional[Callable] = None) -> Dict[str, str]:
        """
        批量決策 AI 玩家的行動 (如白天投票)。
        一次性向 LLM 傳送所有 AI 的角色資訊與局勢，要求回傳 JSON 格式的決策結果。

        Args:
            players_info: Dict[AI玩家名稱, AI角色] (例如: {"AI_1": "平民", "AI_2": "狼人"})
            game_context: 當前局勢描述。
            valid_targets: 合法的目標 ID 列表。
            speech_history: 相關的發言歷史。
        Returns:
            Dict[str, str]: Dict[AI玩家名稱, 目標ID 或 'no']。
        """
        if not players_info:
            return {}

        history_text = ""
        if speech_history:
            history_text = "\n本輪發言/討論紀錄：\n" + "\n".join(speech_history)

        players_list_str = "\n".join([f"- {name} (身分: {role})" for name, role in players_info.items()])

        prompt = f"""
# 批量投票決策
你正在玩狼人殺。你需要同時為以下 AI 玩家做出投票決策：
{players_list_str}

當前局勢：{game_context}
可以選擇的目標（玩家編號）有：{valid_targets}。
{history_text}

# 策略指導與規則
- 每個 AI 玩家都必須依據其「身分」做出最符合其陣營利益的投票決策。
- 狼人應該嘗試把票投給好人，好人應該嘗試把票投給狼人或有嫌疑的人。
- 每個 AI 玩家「只能」從「可選擇目標」中選擇一個編號。
- 如果某個 AI 認為資訊不足以做出判斷，可以選擇棄票（回傳 "no"）。
- 不要虛構理由，只能依據提供的局勢和發言紀錄。

# 輸出格式
請「只」回傳一個 JSON 格式的物件，鍵 (key) 是 AI 玩家名稱，值 (value) 是選擇的目標編號（字串型態）或 "no"。
不要輸出任何其他解釋、分析過程或 Markdown 標記。
範例輸出格式：
{{
    "AI_1": "2",
    "AI_2": "no",
    "AI_3": "5"
}}
"""
        response = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="high")

        # Parse JSON
        results = {}
        try:
            # 尋找 JSON object
            json_match = JSON_OBJECT_PATTERN.search(response)
            if json_match:
                json_str = json_match.group()
                import json
                parsed_json = json.loads(json_str)
                valid_set = {str(t) for t in valid_targets} if valid_targets else set()
                for name, target in parsed_json.items():
                    target_str = str(target).strip().lower().replace(".", "")
                    if "no" in target_str:
                        results[name] = "no"
                    else:
                        match = DIGIT_PATTERN.search(target_str)
                        if match:
                            target_val = match.group()
                            if valid_targets and target_val not in valid_set:
                                logger.warning(f"AI batch returned invalid target {target_val} for player {name} (not in {valid_targets}). Falling back to 'no'.")
                                results[name] = "no"
                            else:
                                results[name] = target_val
                        else:
                            results[name] = "no"
            else:
                logger.error(f"Failed to find JSON in batch action response: {response}")
                # Fallback to "no" for all
                results = {name: "no" for name in players_info.keys()}
        except Exception as e:
            logger.error(f"Error parsing batch action JSON: {e}\nResponse: {response}")
            results = {name: "no" for name in players_info.keys()}

        # 確保所有輸入的玩家都有結果
        for name in players_info.keys():
            if name not in results:
                results[name] = "no"

        return results

    def _get_phase_name(self, game_context: str) -> str:
        """
        根據遊戲天數判斷遊戲階段 (early/mid/late)。
        用於選擇對應的策略指南。
        """
        day_match = DAY_PATTERN.search(game_context)
        if day_match:
            day = int(day_match.group(1))
            if day <= 2:
                return "early"
            elif day <= 4:
                return "mid"
            else:
                return "late"
        return "early"

    async def get_ai_speech(self, player_id: int, role: str, game_context: str, speech_history: Optional[List[str]] = None, retry_callback: Optional[Callable] = None, round_num: int = 1) -> str:
        """
        生成 AI 玩家的發言。

        Args:
            speech_history: 本輪之前的玩家發言紀錄。
            round_num: 目前發言回合 (1 或 2)。
        """
        # 第一輪的第一位發言者，且歷史紀錄為空時才是首置位
        is_first_speaker = not bool(speech_history) and round_num == 1

        strategy_info = ROLE_STRATEGIES.get(role, {})
        speech_style = strategy_info.get("speech_style", "自然")
        objective = strategy_info.get("objective", "獲得勝利")
        speech_guide = strategy_info.get("speech_guide", "")
        reasoning_guide = strategy_info.get("reasoning_guide", "")

        # 獲取階段性策略
        phase = self._get_phase_name(game_context)
        phase_guides = strategy_info.get("phase_guide", {})
        current_phase_guide = phase_guides.get(phase, "")
        phase_labels = {"early": "前期（Day 1-2）", "mid": "中期（Day 3-4）", "late": "殘局（Day 5+）"}
        phase_label = phase_labels.get(phase, "前期")

        # 根據發言順序構建動態限制
        if is_first_speaker:
            scene_restriction = """
# 當前場景限制（最重要的一點）
**現在輪到你發言。你是本輪的「第 1 位」發言者（首置位）。**
**在你之前「沒有任何玩家」發過言。**

**嚴禁捏造資訊**：你只能根據上方「角色設定」所提供的資訊發言。
禁止聲稱你擁有任何未明確列出的查驗結果、守護記錄、或其他資訊。
如果你的身分沒有任何夜晚資訊可報，就誠實表達「目前沒資訊」。
"""
            logic_restriction = """
# 思考邏輯與限制
1. **絕對禁止** 說「我同意前面玩家的說法」或「聽到有人說...」，因為你是第一個，這會讓你產生幻覺。
2. 因為你是第一個，場上還沒有邏輯資訊。請根據你的身分選擇策略：
   - **如果你有夜晚資訊（神職）**：可以選擇起跳報資訊，或者隱藏身分先觀察。
   - **如果你沒有夜晚資訊（平民）**：針對昨晚的死亡情況做評論，表達你的初步判斷。不要只是說「沒資訊」就結束——至少對局勢提出一個觀點或問題。
   - **如果你是狼人**：選擇偽裝策略。可以發起一個話題引導討論方向，或者低調模仿平民。
3. 你的目標是：符合你所屬陣營的最大利益，並引導局勢（或隱藏自己）。
"""
        else:
            history_text = "\n".join(speech_history) if speech_history else ""
            scene_restriction = f"""
# 當前場景限制
這是白天的第 {round_num} 輪發言。
在你之前已經有 {len(speech_history) if speech_history else 0} 筆發言紀錄。
以下是所有發言紀錄：
{history_text}
"""
            round_logic = ""
            if round_num == 2:
                 round_logic = """
   - **因為這是第二輪討論**：你必須做出更明確的判斷。如果第一輪有人攻擊你，你必須強烈反擊。你必須明確給出你心中的狼坑，並說出你這輪想把票投給誰。
"""

            logic_restriction = f"""
# 思考邏輯與限制
1. 你必須參考前面玩家的發言內容。具體做法：
   - 選擇 1-2 位玩家，引用他們的觀點（使用「X 號說...」的格式）。
   - 明確表達你是同意還是反對，並給出理由。
2. 你可以選擇：
   - 站邊：支持某位玩家的邏輯，攻擊另一位。
   - 質疑：指出某位玩家發言中的矛盾或可疑之處。
   - 辯解：如果之前有人懷疑你，回應他的質疑。
   - 歸票：明確說出你認為應該票誰。
3. 你的發言必須有「落點」——最後要給出一個明確的態度或結論。{round_logic}
4. 你的目標是：符合你所屬陣營的最大利益，並引導局勢（或隱藏自己）。

**嚴禁捏造資訊**：你只能引用上方「發言紀錄」中實際出現的內容。
禁止聲稱任何玩家說了紀錄中沒有的話。
禁止虛構查驗結果、守護資訊、或任何未明確提供的遊戲事件。
"""

        prompt = f"""
# 角色設定
你是狼人殺遊戲中的玩家，你的編號是 {player_id} 號。
你的真實身分是【{role}】。
{game_context}

你的發言風格：{speech_style}
你的主要目標：{objective}

# 角色策略
{speech_guide}

# 當前階段策略（{phase_label}）
{current_phase_guide}

{scene_restriction}

# 思考步驟（在心中完成以下分析，不要將分析過程輸出到發言中）
{reasoning_guide}
綜合以上分析，決定你的發言策略，然後直接輸出你的發言內容。

# 你的發言任務
請進行發言（40-60字），語氣要自然，像真人玩家一樣（可以使用口語、語助詞）。
你的發言必須包含至少一個具體的觀點或判斷，不要空泛地划水。
嚴禁暴露你是 AI。

# ⚠️ 防止幻覺規則（最高優先級）
- 你「只能」使用本提示中明確提供的資訊。
- 不可捏造任何遊戲事件、玩家發言、查驗結果或行動。
- 如果你不確定某件事，請說「我不確定」或「我沒有資訊」，而非編造內容。

{logic_restriction}

請開始你的發言（只輸出發言內容，不要輸出分析過程）：
"""
        response = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="high")
        return self._truncate_response(response)

    async def get_ai_last_words(self, player_id: str, role: str, game_context: str, speech_history: Optional[List[str]] = None, retry_callback: Optional[Callable] = None) -> str:
        """
        生成 AI 玩家被處決後的遺言。
        """
        strategy_info = ROLE_STRATEGIES.get(role, {})
        speech_style = strategy_info.get("speech_style", "自然")
        objective = strategy_info.get("objective", "獲得勝利")

        prompt = f"""
# 角色設定
你是狼人殺遊戲中的玩家，你的編號是 {player_id} 號。
你的真實身分是【{role}】。
{game_context}

# 當前狀況
**你剛剛被投票處決了。**
現在是你發表「遺言」的時間。這是你對場上玩家說的最後一句話。

你的發言風格：{speech_style}
你的主要目標：{objective}

# 思考邏輯
1. 根據你的陣營決定策略：
   - **好人陣營**：誠懇地告訴大家你是好人，提醒大家注意誰是狼，或者分析剛才的票型。
   - **狼人陣營**：偽裝成好人被誤殺的樣子，表現出憤怒、委屈，或者繼續誤導好人去推別人。
2. 參考剛才的局勢（誰投了你？誰救了你？）。
3. 這是最後的機會，讓大家相信你的身分。

# 你的任務
請簡短地發表遺言（30-50字）。
語氣要符合你的角色設定（{speech_style}）。
嚴禁暴露你是 AI。

請直接輸出遺言內容：
"""
        response = await self.generate_response(prompt, retry_callback=retry_callback, reasoning_effort="high")
        return self._truncate_response(response)

# 全域實例
ai_manager = AIManager()
