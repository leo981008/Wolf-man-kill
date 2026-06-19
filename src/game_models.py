import enum
from typing import Dict, List, Optional
import discord

class Faction(enum.Enum):
    WOLF = "狼人陣營"
    GOD = "神職陣營"
    VILLAGER = "平民陣營"
    NONE = "旁觀天神"

class Role:
    name = "未定義"
    faction = Faction.NONE

    def __init__(self):
        pass

class Werewolf(Role):
    name = "狼人"
    faction = Faction.WOLF

class Seer(Role):
    name = "預言家"
    faction = Faction.GOD

class Witch(Role):
    name = "女巫"
    faction = Faction.GOD

    def __init__(self):
        super().__init__()
        self.has_heal = True
        self.has_poison = True

class Guard(Role):
    name = "守衛"
    faction = Faction.GOD

    def __init__(self):
        super().__init__()
        self.last_guarded: Optional[int] = None

class Hunter(Role):
    name = "獵人"
    faction = Faction.GOD

    def __init__(self):
        super().__init__()
        self.can_shoot = True

class Idiot(Role):
    name = "白痴"
    faction = Faction.GOD

    def __init__(self):
        super().__init__()
        self.revealed = False

class Villager(Role):
    name = "平民"
    faction = Faction.VILLAGER

class Spectator(Role):
    name = "旁觀天神"
    faction = Faction.NONE

ROLE_MAPPING = {
    "狼人": Werewolf,
    "預言家": Seer,
    "女巫": Witch,
    "守衛": Guard,
    "獵人": Hunter,
    "白痴": Idiot,
    "平民": Villager,
    "旁觀天神": Spectator
}

class Player:
    def __init__(self, user: discord.User | discord.Member, number: int, is_ai: bool = False):
        self.user = user
        self.number = number
        self.is_ai = is_ai
        self.role: Optional[Role] = None
        self.is_alive = True
        self.death_reason: Optional[str] = None
        self.has_last_words = False

        # AI Specific Memory
        self.ai_memory: List[str] = []

    def __str__(self):
        return f"[{self.number}號] {self.user.display_name}"

class GamePhase(enum.Enum):
    WAITING = "等待中"
    NIGHT = "夜晚"
    NIGHT_WITCH_PHASE = "夜晚(女巫)"
    DAY = "白天"
    ENDED = "已結束"

class GameState:
    def __init__(self, channel: discord.TextChannel, creator: discord.User | discord.Member):
        self.channel = channel
        self.creator = creator
        self.players: Dict[int, Player] = {}
        self.phase = GamePhase.WAITING
        self.day_count = 0

        # State tracking
        self.wolf_count = 0
        self.god_count = 0
        self.villager_count = 0

        # Night actions
        self.night_kills: List[int] = []
        self.witch_heal: Optional[int] = None
        self.witch_poison: Optional[int] = None
        self.guard_protect: Optional[int] = None

        # History
        self.speech_history: List[str] = []

    def add_player(self, player: Player):
        self.players[player.number] = player

    def remove_player(self, number: int):
        if number in self.players:
            player = self.players[number]
            if player.role:
                if player.role.faction == Faction.WOLF:
                    self.wolf_count = max(0, self.wolf_count - 1)
                elif player.role.faction == Faction.GOD:
                    self.god_count = max(0, self.god_count - 1)
                elif player.role.faction == Faction.VILLAGER:
                    self.villager_count = max(0, self.villager_count - 1)
            del self.players[number]

    def get_alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_alive and p.role and p.role.faction != Faction.NONE]

    def get_alive_numbers(self) -> List[int]:
        return [p.number for p in self.get_alive_players()]

    def check_game_over(self) -> Optional[Faction]:
        if self.phase == GamePhase.WAITING:
            return None

        alive_wolves = sum(1 for p in self.get_alive_players() if p.role.faction == Faction.WOLF)
        alive_gods = sum(1 for p in self.get_alive_players() if p.role.faction == Faction.GOD)
        alive_villagers = sum(1 for p in self.get_alive_players() if p.role.faction == Faction.VILLAGER)

        if alive_wolves == 0:
            return Faction.VILLAGER

        if self.god_count > 0 and alive_gods == 0:
            return Faction.WOLF
        if self.villager_count > 0 and alive_villagers == 0:
            return Faction.WOLF

        return None
