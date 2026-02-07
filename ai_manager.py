import os
from dotenv import load_dotenv
import asyncio
import json
import re
import aiohttp
from collections import OrderedDict
from ai_strategies import ROLE_STRATEGIES

load_dotenv()

DIGIT_PATTERN = re.compile(r'\d+')

CACHE_FILE = "ai_cache.json"

class AIManager:
    def __init__(self):
        self.provider = os.getenv('AI_PROVIDER', 'gemini').lower()
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')
        self.ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.session = None

        print(f"AI Manager initialized. Provider: {self.provider}")
        if self.provider == 'ollama':
            print(f"Ollama Model: {self.ollama_model}, Host: {self.ollama_host}")

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

    async def _generate_with_gemini(self, prompt):
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
                print(f"Gemini CLI Error: {error_msg}")
                return ""
        except Exception as e:
            print(f"Gemini Execution Error: {e}")
            return ""

    async def generate_response(self, prompt):
        """Generic async wrapper for generating content"""
        if self.provider == 'ollama':
            return await self._generate_with_ollama(prompt)

        # Default to Gemini (via CLI)
        return await self._generate_with_gemini(prompt)

    async def generate_role_template(self, player_count, existing_roles):
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
        """

        response_text = await self.generate_response(prompt)
        try:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
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
            print(f"Invalid generated roles: {roles}")
            return []
        except Exception as e:
            print(f"Role generation failed: {e}\nResponse: {response_text}")
            return []

    async def generate_narrative(self, event_type, context, language="zh-TW"):
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

        事件類型：{event_type}
        詳細資訊：{context}
        """
        response = await self.generate_response(prompt)

        self.narrative_cache[cache_key] = response

        # Evict oldest if over limit
        if len(self.narrative_cache) > 100:
            self.narrative_cache.popitem(last=False)

        return response

    async def get_ai_action(self, role, game_context, valid_targets):
        """
        Decides an action for an AI player.
        """
        strategy_info = ROLE_STRATEGIES.get(role, {})
        action_guide = strategy_info.get("action_guide", "")

        prompt = f"""
        你正在玩狼人殺。你的身分是：{role}。
        當前局勢：{game_context}
        你可以選擇的目標（玩家編號）有：{valid_targets}。

        策略建議：{action_guide}

        請根據你的角色勝利條件做出最佳選擇。

        請只回傳你選擇的目標編號（數字）。
        如果你決定不行動、空守或棄票，請回傳 'no'。
        只回傳結果，不要解釋。
        """
        response = await self.generate_response(prompt)
        clean = response.strip().lower().replace(".", "")

        if "no" in clean:
            return "no"

        match = DIGIT_PATTERN.search(clean)
        if match:
            return match.group()
        return "no"

    async def get_ai_speech(self, player_id, role, game_context, speech_history=None):
        """
        Generates a speech for an AI player.
        speech_history: List of strings (previous speeches in the round).
        """
        history_text = ""
        if speech_history:
            history_text = "\n本輪發言紀錄：\n" + "\n".join(speech_history)

        strategy_info = ROLE_STRATEGIES.get(role, {})
        speech_style = strategy_info.get("speech_style", "自然")
        objective = strategy_info.get("objective", "獲得勝利")
        speech_guide = strategy_info.get("speech_guide", "")

        prompt = f"""
        你正在玩狼人殺。你是 {player_id} 號玩家。
        你的真實身分是：{role}。

        你的發言風格應該是：{speech_style}。
        你的主要目標是：{objective}。

        詳細指導原則：
        {speech_guide}

        當前局勢：{game_context}
        {history_text}

        現在輪到你發言。請簡短發言（50字以內），分析局勢或為自己辯解。
        請使用繁體中文，語氣要自然，像真人玩家一樣。
        不要暴露你是 AI。
        """
        return await self.generate_response(prompt)

# Global instance
ai_manager = AIManager()
