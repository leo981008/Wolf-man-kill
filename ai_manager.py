import os
from dotenv import load_dotenv
import asyncio
import json
import re
import aiohttp
import time
from collections import OrderedDict
from ai_strategies import ROLE_STRATEGIES

load_dotenv()

DIGIT_PATTERN = re.compile(r'\d+')

CACHE_FILE = "ai_cache.json"

class RateLimitError(Exception):
    """Exception raised when API rate limit is exceeded."""
    pass

class RateLimiter:
    """
    Token Bucket implementation for rate limiting.
    """
    def __init__(self, rate, capacity):
        self.rate = rate  # Tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens += elapsed * self.rate
            if self.tokens > self.capacity:
                self.tokens = self.capacity
            self.last_update = now

            if self.tokens >= 1:
                self.tokens -= 1
                return

            # Calculate wait time needed to get 1 token
            missing = 1 - self.tokens
            wait_time = missing / self.rate

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            # After waiting, we have exactly 0 tokens left (we consumed the one we waited for)
            self.tokens = 0
            self.last_update = time.monotonic()

class AIManager:
    def __init__(self):
        self.provider = os.getenv('AI_PROVIDER', 'gemini').lower()
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')
        self.ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-pro')
        self.session = None

        print(f"AI Manager initialized. Provider: {self.provider}")
        if self.provider == 'ollama':
            print(f"Ollama Model: {self.ollama_model}, Host: {self.ollama_host}")
        elif self.provider == 'gemini-api':
            print(f"Gemini API Model: {self.gemini_model}")

        # Rate Limiter: 15 RPM = 0.25 requests/sec (1 request every 4 seconds)
        # Capacity 1 ensures strict spacing.
        self.rate_limiter = RateLimiter(rate=15/60.0, capacity=1.0)

        self.narrative_cache = OrderedDict()
        self.role_template_cache = OrderedDict()
        self._load_cache()

    def _load_cache(self):
        if not os.path.exists(CACHE_FILE):
            return

        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for entry in data:
                # Entry format: {"player_count": 5, "existing_roles": [...], "roles": [...]}
                if not all(k in entry for k in ("player_count", "existing_roles", "roles")):
                    continue

                player_count = entry["player_count"]
                existing_roles = tuple(entry["existing_roles"])
                roles = entry["roles"]

                key = (player_count, existing_roles)
                self.role_template_cache[key] = roles

            print(f"Loaded {len(self.role_template_cache)} entries from cache.")
        except Exception as e:
            print(f"Failed to load cache: {e}")

    def _save_cache(self):
        try:
            data = []
            for (player_count, existing_roles), roles in self.role_template_cache.items():
                data.append({
                    "player_count": player_count,
                    "existing_roles": list(existing_roles),
                    "roles": roles
                })

            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Failed to save cache: {e}")

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def _generate_with_ollama(self, prompt):
        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False
        }
        try:
            session = await self.get_session()
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "").strip()
                else:
                    error_text = await response.text()
                    print(f"Ollama API Error: {response.status} - {error_text}")
                    return ""
        except Exception as e:
            print(f"Ollama Connection Error: {e}")
            return ""

    async def _generate_with_gemini_cli(self, prompt):
        """Executes gemini-cli via subprocess."""
        try:
            # Create subprocess: gemini -p "prompt"
            # Using list of arguments avoids shell injection risks
            process = await asyncio.create_subprocess_exec(
                'gemini', '-p', prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                return stdout.decode().strip()
            else:
                error_msg = stderr.decode().strip()
                # Detect rate limit in stderr
                if "429" in error_msg or "ResourceExhausted" in error_msg:
                    raise RateLimitError(f"Gemini CLI 429: {error_msg}")

                print(f"Gemini CLI Error: {error_msg}")
                return ""
        except RateLimitError:
            raise
        except Exception as e:
            print(f"Gemini Execution Error: {e}")
            return ""

    async def _generate_with_gemini_api(self, prompt):
        """Executes Gemini via Google API."""
        if not self.gemini_api_key:
            print("Gemini API Key is missing.")
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
                    print(f"Gemini API Error: {response.status} - {error_text}")
                    return ""
        except RateLimitError:
            raise
        except Exception as e:
            print(f"Gemini API Connection Error: {e}")
            return ""

    async def generate_response(self, prompt, retry_callback=None):
        """
        Generic async wrapper for generating content with Rate Limiting and Retry logic.
        """
        # Define the generation task based on provider
        async def task():
            if self.provider == 'ollama':
                return await self._generate_with_ollama(prompt)
            elif self.provider == 'gemini-api':
                return await self._generate_with_gemini_api(prompt)
            elif self.provider == 'gemini-cli' or self.provider == 'gemini':
                return await self._generate_with_gemini_cli(prompt)
            else:
                print(f"Unknown provider: {self.provider}, defaulting to Gemini CLI")
                return await self._generate_with_gemini_cli(prompt)

        # Retry logic with Rate Limiting
        max_retries = 3
        base_delay = 4.0 # Seconds

        for attempt in range(max_retries + 1):
            try:
                # Proactive Rate Limiting (only for Gemini)
                if 'gemini' in self.provider:
                    await self.rate_limiter.acquire()

                return await task()

            except RateLimitError as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    print(f"Rate limit hit. Retrying in {delay}s... (Attempt {attempt+1}/{max_retries})")

                    if retry_callback:
                        try:
                            # Invoke callback to notify user, but don't fail if it fails
                            if asyncio.iscoroutinefunction(retry_callback):
                                await retry_callback()
                            else:
                                retry_callback()
                        except Exception as cb_e:
                            print(f"Retry callback failed: {cb_e}")

                    await asyncio.sleep(delay)
                else:
                    print(f"Rate limit exceeded after {max_retries} retries: {e}")
                    return ""
            except Exception as e:
                print(f"Unexpected error during generation: {e}")
                return ""
        return ""

    async def generate_role_template(self, player_count, existing_roles, retry_callback=None):
        """
        Generates a balanced role list for a given player count.
        """
        # Create cache key
        cache_key = (player_count, tuple(sorted(existing_roles)))

        if cache_key in self.role_template_cache:
            self.role_template_cache.move_to_end(cache_key)
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

        response_text = await self.generate_response(prompt, retry_callback=retry_callback)
        try:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            # Try to find JSON array if extra text exists
            start = clean_text.find('[')
            end = clean_text.rfind(']')
            if start != -1 and end != -1:
                clean_text = clean_text[start:end+1]

            roles = json.loads(clean_text)
            if isinstance(roles, list) and len(roles) == player_count:
                # Validate roles exist
                existing_roles_set = set(existing_roles)
                if all(r in existing_roles_set for r in roles):
                    # Cache the result
                    self.role_template_cache[cache_key] = roles
                    if len(self.role_template_cache) > 100:
                        self.role_template_cache.popitem(last=False)
                    self._save_cache()
                    return roles
            if response_text: # Only print invalid if we actually got a response
                print(f"Invalid generated roles: {roles}")
            return []
        except Exception as e:
            print(f"Role generation failed: {e}\nResponse: {response_text}")
            return []

    async def generate_narrative(self, event_type, context, language="zh-TW", retry_callback=None):
        """
        Generates flavor text for game events.
        """
        # Ensure context is hashable and limit cache size
        cache_key = (event_type, str(context), language)
        if cache_key in self.narrative_cache:
            # Move to end to mark as recently used
            self.narrative_cache.move_to_end(cache_key)
            return self.narrative_cache[cache_key]

        prompt = f"""
        你是一個狼人殺遊戲的主持人（上帝）。
        請根據以下情境，生成一段富有氛圍的旁白（約 30-50 字）。
        請直接輸出旁白內容，不要加上「主持人：」等前綴。

        ⚠️ 嚴格限制：
        - 你只能根據下方提供的事件資訊生成旁白。
        - 嚴禁透露任何玩家的身分、角色、或未公開的遊戲資訊。
        - 嚴禁編造未發生的事件或添加下方未提及的細節。
        - 只描述氛圍和情境，不要加入具體的遊戲判斷。

        事件類型：{event_type}
        詳細資訊：{context}
        """
        response = await self.generate_response(prompt, retry_callback=retry_callback)

        if response:
            self.narrative_cache[cache_key] = response
            # Evict oldest if over limit
            if len(self.narrative_cache) > 100:
                self.narrative_cache.popitem(last=False)

        return response

    async def get_ai_action(self, role, game_context, valid_targets, speech_history=None, retry_callback=None):
        """
        Decides an action for an AI player.
        """
        strategy_info = ROLE_STRATEGIES.get(role, {})
        action_guide = strategy_info.get("action_guide", "")

        history_text = ""
        if speech_history:
            history_text = "\n本輪發言/討論紀錄：\n" + "\n".join(speech_history)

        prompt = f"""
        你正在玩狼人殺。你的身分是：{role}。
        當前局勢：{game_context}
        你可以選擇的目標（玩家編號）有：{valid_targets}。
        {history_text}

        策略建議：{action_guide}

        請根據你的角色勝利條件做出最佳選擇。

        ⚠️ 行動規則（必須遵守）：
        - 你「只能」從上方列出的「可選擇目標」中選擇一個編號。
        - 不要選擇不在目標列表中的編號。
        - 你只能依據上方提供的「當前局勢」和「發言紀錄」做出判斷，不可虛構理由。
        - 如果資訊不足以做出判斷，請回傳 'no'。

        請只回傳你選擇的目標編號（數字）。
        如果你決定不行動、空守或棄票，請回傳 'no'。
        只回傳結果，不要解釋。
        """
        response = await self.generate_response(prompt, retry_callback=retry_callback)
        clean = response.strip().lower().replace(".", "")

        if "no" in clean:
            return "no"

        match = DIGIT_PATTERN.search(clean)
        if match:
            return match.group()
        return "no"

    async def get_ai_speech(self, player_id, role, game_context, speech_history=None, retry_callback=None):
        """
        Generates a speech for an AI player.
        speech_history: List of strings (previous speeches in the round).
        """
        is_first_speaker = not bool(speech_history)

        strategy_info = ROLE_STRATEGIES.get(role, {})
        speech_style = strategy_info.get("speech_style", "自然")
        objective = strategy_info.get("objective", "獲得勝利")
        speech_guide = strategy_info.get("speech_guide", "")

        # Construct Dynamic Logic based on position
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
   - **如果是好人**：請針對昨晚的死亡情況做簡單評論，或者直接承認「目前沒資訊，先聽後面怎麼說」，然後過麥（划水）。
   - **如果是狼人/神職**：你可以選擇發起一個假話題，或者為了安全起見，裝作無知的平民「划水」。
3. 你的目標是：符合你所屬陣營的最大利益，並引導局勢（或隱藏自己）。
"""
        else:
            history_text = "\n".join(speech_history)
            scene_restriction = f"""
# 當前場景限制
在你之前已經有 {len(speech_history)} 位玩家發言了。
以下是他們的發言紀錄：
{history_text}
"""
            logic_restriction = """
# 思考邏輯與限制
1. 請仔細分析前面玩家的發言，尋找邏輯漏洞或矛盾點。
2. 你可以選擇：
   - 同意或反駁某位玩家的觀點。
   - 提出新的懷疑對象。
   - 為自己辯解（如果被懷疑）。
3. 你的目標是：符合你所屬陣營的最大利益，並引導局勢（或隱藏自己）。

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

詳細角色指導：
{speech_guide}

{scene_restriction}

# 你的發言任務
請進行發言（80字左右），語氣要自然，像真人玩家一樣（可以使用口語、語助詞）。
嚴禁暴露你是 AI。

# ⚠️ 防止幻覺規則（最高優先級）
- 你「只能」使用本提示中明確提供的資訊。
- 不可捏造任何遊戲事件、玩家發言、查驗結果或行動。
- 如果你不確定某件事，請說「我不確定」或「我沒有資訊」，而非編造內容。

{logic_restriction}

請開始你的發言：
"""
        return await self.generate_response(prompt, retry_callback=retry_callback)

# Global instance
ai_manager = AIManager()
