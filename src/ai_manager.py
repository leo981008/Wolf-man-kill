import aiohttp
import json
import os
import re
from typing import Dict, Any, List, Optional
from src.utils import logger

class AIManager:
    def _clean_text(self, text: str) -> str:
        """Remove <think>...</think> tags and their contents from the generated text."""
        if not text:
            return text
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    def __init__(self, host: str = None, model: str = None):
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        if self.nvidia_api_key:
            self.mode = "nvidia"
            self.model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
            self.api_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        else:
            self.mode = "ollama"
            self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
            self.model = model or "gemma4:latest"
            self.api_url = f"{self.host}/api/generate"
            
        self._json_object_pattern = re.compile(r'\{.*?\}', re.DOTALL)
        self._json_array_pattern = re.compile(r'\[.*\]', re.DOTALL)

    async def _generate(self, prompt: str, system: str = "") -> Optional[str]:
        if self.mode == "nvidia":
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.5,
                "max_tokens": 1024
            }
            headers = {
                "Authorization": f"Bearer {self.nvidia_api_key}",
                "Content-Type": "application/json"
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, json=payload, headers=headers, timeout=60) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data.get("choices") and len(data["choices"]) > 0:
                                content = data["choices"][0].get("message", {}).get("content", "")
                                return self._clean_text(content)
                            return ""
                        else:
                            text = await response.text()
                            logger.error(f"NVIDIA API error ({response.status}): {text}")
                            return None
            except Exception as e:
                logger.error(f"Error connecting to NVIDIA API: {e}")
                return None
        else:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "system": system,
                "stream": False
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.api_url, json=payload, timeout=60) as response:
                        if response.status == 200:
                            data = await response.json()
                            return self._clean_text(data.get("response", ""))
                        else:
                            text = await response.text()
                            logger.error(f"Ollama API error ({response.status}): {text}")
                            return None
            except Exception as e:
                logger.error(f"Error connecting to Ollama: {e}")
                return None

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        match = self._json_object_pattern.search(text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON object: {e}\nText: {text}")
        return None

    async def decide_roles_for_players(self, player_count: int, all_roles: List[str]) -> Optional[Dict[str, int]]:
        system_prompt = (
            "你是一個狼人殺遊戲的平衡大師。你的任務是為非標準人數的對局設計合理的角色配置（板子）。\n"
            "這是一個「屠邊局」（狼人殺光所有神職，或殺光所有平民即獲勝；好人則是淘汰所有狼人獲勝）。\n"
            "請確保狼人陣營與好人陣營（神職+平民）的實力平衡。\n"
            "可用角色包含：狼人、預言家、女巫、獵人、守衛、白痴、平民。\n"
            "多餘的玩家可以設定為「旁觀天神」（不參與遊戲）。\n"
            "請以 JSON 格式回傳，格式為: {\"狼人\": 2, \"預言家\": 1, ...}"
        )
        prompt = f"請為 {player_count} 名玩家設計平衡的角色配置。可用角色：{', '.join(all_roles)}"
        response = await self._generate(prompt, system=system_prompt)
        if not response:
            return None
        return self._extract_json_object(response)

    async def generate_night_action(self, role: str, context: str, valid_targets: List[int]) -> Optional[Dict[str, Any]]:
        system_prompt = (
            f"你在玩狼人殺，你的身分是【{role}】。現在是夜晚行動時間。\n"
            "請根據目前的遊戲狀態，決定你要對誰使用技能，並給出你的理由。\n"
            "請務必以 JSON 格式回覆，包含 'target' (整數) 與 'reason' (字串) 兩個欄位。\n"
            f"有效的目標編號：{valid_targets}。如果你不想使用技能，請將 target 設為 0 或 null。\n"
        )
        prompt = f"目前遊戲狀態：\n{context}\n\n請決定你的夜間行動："
        response = await self._generate(prompt, system=system_prompt)
        if not response:
            return None
        return self._extract_json_object(response)

    async def generate_witch_action(self, context: str, valid_targets: List[int]) -> Optional[Dict[str, Any]]:
        system_prompt = (
            "你在玩狼人殺，你的身分是【女巫】。現在是女巫行動時間。\n"
            "請根據目前的遊戲狀態，決定你要使用解藥還是毒藥，並給出理由。\n"
            "請務必以 JSON 格式回覆，包含 'heal_target' (整數, 不救設為0), 'poison_target' (整數, 不毒設為0), 與 'reason' (字串)。\n"
            f"有效的毒藥目標編號：{valid_targets}。\n"
        )
        prompt = f"目前遊戲狀態：\n{context}\n\n請決定你的行動："
        response = await self._generate(prompt, system=system_prompt)
        if not response:
            return None
        return self._extract_json_object(response)

    async def generate_day_speech(self, role: str, player_number: int, context: str, history: str) -> Optional[str]:
        system_prompt = (
            f"你在玩狼人殺，你的編號是 {player_number} 號，你的身分是【{role}】。\n"
            "現在是白天發言時間，請根據你昨晚的行動結果、你的個人記憶、白天的死訊以及其他玩家的發言，發表你的看法。\n"
            "請表現得像一個真實的玩家，你可以偽裝、質疑他人，或是分享你的邏輯推理。\n"
            "請控制發言在 100 字以內。\n"
            "請直接輸出你的發言內容，不需要 JSON 格式，也不要加上引號或其他前綴。"
        )
        prompt = f"目前遊戲狀態與你的記憶：\n{context}\n\n之前的發言紀錄：\n{history}\n\n請開始你的發言："
        return await self._generate(prompt, system=system_prompt)

    async def generate_vote(self, role: str, player_number: int, context: str, valid_targets: List[int]) -> Optional[int]:
        system_prompt = (
            f"你在玩狼人殺，你的編號是 {player_number} 號，你的身分是【{role}】。\n"
            "現在是白天投票時間。請根據目前的局勢與大家的發言，決定你要把票投給誰。\n"
            f"有效的投票目標編號：{valid_targets}。如果不投票或棄票，請投 0。\n"
            "請只輸出一個代表目標編號的整數，不要包含任何其他文字。"
        )
        prompt = f"目前遊戲狀態與記憶：\n{context}\n\n請投票："
        response = await self._generate(prompt, system=system_prompt)
        if not response:
            return None
        match = re.search(r'\b\d+\b', response)
        if match:
            target = int(match.group())
            if target in valid_targets or target == 0:
                return target
        return 0
