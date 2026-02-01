import os
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio
import json
import re
import aiohttp

load_dotenv()

# Configure Gemini
api_key = os.getenv('GEMINI_API_KEY')
if api_key:
    genai.configure(api_key=api_key)

# Model configuration
GENERATION_CONFIG = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 1024,
}

SAFETY_SETTINGS = [
    {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_ONLY_HIGH"
    },
    {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_ONLY_HIGH"
    },
    {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_ONLY_HIGH"
    },
    {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_ONLY_HIGH"
    },
]

DIGIT_PATTERN = re.compile(r'\d+')

class AIManager:
    def __init__(self):
        self.provider = os.getenv('AI_PROVIDER', 'gemini').lower()
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')
        self.ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')

        self.model = None
        if self.provider == 'gemini':
            if api_key:
                self.model = genai.GenerativeModel(model_name="gemini-1.5-flash",
                                                  generation_config=GENERATION_CONFIG,
                                                  safety_settings=SAFETY_SETTINGS)
            else:
                 print("Warning: GEMINI_API_KEY not found. AI features disabled for Gemini.")

        print(f"AI Manager initialized. Provider: {self.provider}")
        if self.provider == 'ollama':
            print(f"Ollama Model: {self.ollama_model}, Host: {self.ollama_host}")

    async def _generate_with_ollama(self, prompt):
        url = f"{self.ollama_host}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False
        }
        try:
            async with aiohttp.ClientSession() as session:
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

    async def generate_response(self, prompt):
        """Generic async wrapper for generating content"""
        if self.provider == 'ollama':
            return await self._generate_with_ollama(prompt)

        # Default to Gemini
        if not self.model:
            return "錯誤：Gemini API Key 未設定，無法生成內容。"

        try:
            # Run blocking API call in executor
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            if response.parts:
                return response.text.strip()
            return ""
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return "" # Fail silently or handle gracefully

    async def generate_role_template(self, player_count, existing_roles):
        """
        Generates a balanced role list for a given player count.
        """
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
                if all(r in existing_roles for r in roles):
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
        prompt = f"""
        你是一個狼人殺遊戲的主持人（上帝）。
        請根據以下情境，生成一段富有氛圍的旁白（約 30-50 字）。
        請直接輸出旁白內容，不要加上「主持人：」等前綴。

        事件類型：{event_type}
        詳細資訊：{context}
        """
        return await self.generate_response(prompt)

    async def get_ai_action(self, role, game_context, valid_targets):
        """
        Decides an action for an AI player.
        """
        prompt = f"""
        你正在玩狼人殺。你的身分是：{role}。
        當前局勢：{game_context}
        你可以選擇的目標（玩家編號）有：{valid_targets}。
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

        prompt = f"""
        你正在玩狼人殺。你是 {player_id} 號玩家。
        你的真實身分是：{role}。
        (如果是狼人，請偽裝成好人；如果是好人，請尋找狼人)。

        當前局勢：{game_context}
        {history_text}

        現在輪到你發言。請簡短發言（50字以內），分析局勢或為自己辯解。
        請使用繁體中文，語氣要自然，像真人玩家一樣。
        不要暴露你是 AI。
        """
        return await self.generate_response(prompt)

# Global instance
ai_manager = AIManager()
