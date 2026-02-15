import asyncio
import uuid
import discord
from collections import deque
from typing import Dict, List, Set, Optional, Any, Union

class AIPlayer:
    def __init__(self, name: str):
        self.id = uuid.uuid4().int >> 96  # 使用 UUID 避免 ID 碰撞
        self.name = name
        self.mention = f"**{name}**"
        self.bot = True
        self.discriminator = "0000"

    async def send(self, content: str):
        pass # AI logic handles input separately

    async def edit(self, mute: bool = False):
        pass

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other: Any) -> bool:
        return hasattr(other, 'id') and self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

class GameState:
    def __init__(self):
        self.players: List[Union[discord.Member, AIPlayer]] = []
        self.roles: Dict[Union[discord.Member, AIPlayer], str] = {}
        self.gods: List[Union[discord.Member, AIPlayer]] = []
        self.votes: Dict[Union[discord.Member, AIPlayer], int] = {}
        self.voted_players: Set[Union[discord.Member, AIPlayer]] = set()
        self.game_active: bool = False
        self.player_ids: Dict[int, Union[discord.Member, AIPlayer]] = {}     # ID -> Member
        self.player_id_map: Dict[Union[discord.Member, AIPlayer], int] = {}  # Member -> ID
        self.witch_potions: Dict[str, bool] = {'antidote': True, 'poison': True}
        self.creator: Optional[Union[discord.Member, discord.User]] = None      # 房主 (用於權限控制)
        self.lock = asyncio.Lock() # 並發控制鎖

        # 發言階段狀態
        self.speaking_queue: deque = deque()
        self.current_speaker: Optional[Union[discord.Member, AIPlayer]] = None
        self.speaking_active: bool = False

        # 新增屬性
        self.game_mode: str = "online" # "online" or "offline"
        self.ai_players: List[AIPlayer] = []
        self.speech_history: List[str] = [] # 儲存本輪發言紀錄
        self.role_to_players: Dict[str, List[Union[discord.Member, AIPlayer]]] = {} # 角色 -> 玩家列表 (優化查找)
        self.day_count: int = 0
        self.last_dead_players: List[str] = []

    def reset(self):
        self.players = []
        self.roles = {}
        self.role_to_players = {}
        self.gods = []
        self.votes = {}
        self.voted_players = set()
        self.game_active = False
        self.player_ids = {}
        self.player_id_map = {}
        self.witch_potions = {'antidote': True, 'poison': True}
        self.creator = None

        self.speaking_queue = deque()
        self.current_speaker = None
        self.speaking_active = False
        self.speech_history = []

        self.game_mode = "online"
        self.ai_players = []
        self.day_count = 0
        self.last_dead_players = []

# Guild ID -> GameState
games: Dict[int, GameState] = {}

def get_game(guild_id: int) -> GameState:
    if guild_id not in games:
        games[guild_id] = GameState()
    return games[guild_id]
