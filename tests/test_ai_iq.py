#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 智商測試程式 (AI IQ Benchmark)
=================================
使用本地 Ollama (gpt-oss:20b) 模擬全 AI 狼人殺對局，
從五大維度量化評分 AI 的決策能力。

用法: python tests/test_ai_iq.py [--games N] [--players N]
"""

# 修正 Windows 終端機 Unicode 編碼問題
import sys
import os
import io

def _setup_encoding():
    """設定 UTF-8 輸出，對管道輸出安全"""
    if sys.platform == 'win32':
        # 只在真正的終端機上 reconfigure，不影響管道
        for stream_name in ('stdout', 'stderr'):
            stream = getattr(sys, stream_name)
            if hasattr(stream, 'reconfigure') and hasattr(stream, 'buffer'):
                try:
                    stream.reconfigure(encoding='utf-8', errors='replace')
                except Exception:
                    # 如果 reconfigure 失敗，用 TextIOWrapper 包裝
                    try:
                        wrapped = io.TextIOWrapper(stream.buffer, encoding='utf-8', errors='replace', line_buffering=True)
                        setattr(sys, stream_name, wrapped)
                    except Exception:
                        pass

_setup_encoding()

import asyncio
import re
import time
import random
import argparse
from dataclasses import dataclass, field
from typing import Optional

# 確保能 import 專案根目錄的模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ai_manager import AIManager

# ═══════════════════════════════════════════════════════════════
# 常數 & 配置
# ═══════════════════════════════════════════════════════════════

WOLF_FACTION = {"狼人", "狼王", "白狼王", "惡靈騎士", "隱狼"}
GOD_FACTION = {"預言家", "女巫", "獵人", "守衛", "白痴", "騎士"}
VILLAGER_FACTION = {"平民", "老流氓"}

# 9人局配置
DEFAULT_ROLES = ["狼人", "狼人", "狼人", "預言家", "女巫", "獵人", "平民", "平民", "平民"]

MAX_DAYS = 8  # 防止無限迴圈

# 顏色碼
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_RED  = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"

# ═══════════════════════════════════════════════════════════════
# 資料結構
# ═══════════════════════════════════════════════════════════════

@dataclass
class SimulatedPlayer:
    """模擬玩家"""
    id: int
    name: str
    role: str
    alive: bool = True

    @property
    def faction(self):
        if self.role in WOLF_FACTION:
            return "wolf"
        elif self.role in GOD_FACTION:
            return "god"
        else:
            return "villager"

    @property
    def is_good(self):
        return self.faction != "wolf"


@dataclass
class ActionRecord:
    """紀錄一次 AI 行動"""
    player_id: int
    role: str
    action_type: str       # 'kill', 'check', 'guard', 'save', 'poison', 'vote'
    target_id: Optional[int]
    valid_targets: list
    raw_response: str = ""
    is_legal: bool = True          # 目標在 valid_targets 中
    is_role_aware: bool = True     # 沒有明顯角色錯誤
    violation_note: str = ""


@dataclass
class SpeechRecord:
    """紀錄一次 AI 發言"""
    player_id: int
    role: str
    speech: str
    is_first_speaker: bool
    char_count: int = 0
    is_empty: bool = False
    has_hallucination: bool = False  # 首位發言卻引用前人
    quality_ok: bool = True          # 字數合格


@dataclass
class VoteRecord:
    """紀錄一次投票"""
    voter_id: int
    voter_role: str
    target_id: Optional[int]
    target_role: Optional[str]
    is_correct: bool = True  # 狼人投好人=正確, 好人投狼人=正確


@dataclass
class GameResult:
    """一場遊戲的結果"""
    winner: str = ""
    day_count: int = 0
    actions: list = field(default_factory=list)
    speeches: list = field(default_factory=list)
    votes: list = field(default_factory=list)
    game_log: list = field(default_factory=list)

# ═══════════════════════════════════════════════════════════════
# 遊戲模擬引擎
# ═══════════════════════════════════════════════════════════════

class GameSimulator:
    """完整模擬一場狼人殺"""

    def __init__(self, ai: AIManager, roles: list = None, verbose: bool = True):
        self.ai = ai
        self.roles_template = roles or DEFAULT_ROLES
        self.verbose = verbose
        self.players: list[SimulatedPlayer] = []
        self.result = GameResult()
        self.day_count = 0
        self.speech_history: list[str] = []
        self.last_dead_names: list[str] = []
        self.witch_potions = {'antidote': True, 'poison': True}
        self.last_guard_target: Optional[int] = None

    def _log(self, msg: str):
        self.result.game_log.append(msg)
        if self.verbose:
            print(msg)

    def setup(self):
        """初始化玩家和角色"""
        roles = list(self.roles_template)
        random.shuffle(roles)
        self.players = []
        for i, role in enumerate(roles):
            p = SimulatedPlayer(id=i + 1, name=f"AI-{i+1}", role=role)
            self.players.append(p)
        self._log(f"\n{C.BOLD}{C.CYAN}{'═'*60}{C.RESET}")
        self._log(f"{C.BOLD}{C.CYAN}  🎮 新遊戲開始！{len(self.players)} 名玩家{C.RESET}")
        self._log(f"{C.BOLD}{C.CYAN}{'═'*60}{C.RESET}")
        for p in self.players:
            faction_color = C.RED if not p.is_good else C.GREEN
            self._log(f"  {p.id}號 {p.name}: {faction_color}{p.role}{C.RESET}")

    @property
    def alive_players(self) -> list[SimulatedPlayer]:
        return [p for p in self.players if p.alive]

    @property
    def alive_ids(self) -> list[int]:
        return [p.id for p in self.alive_players]

    def get_player(self, pid: int) -> Optional[SimulatedPlayer]:
        for p in self.players:
            if p.id == pid:
                return p
        return None

    def kill_player(self, pid: int) -> Optional[SimulatedPlayer]:
        p = self.get_player(pid)
        if p and p.alive:
            p.alive = False
            return p
        return None

    def check_game_over(self) -> Optional[str]:
        """檢查遊戲是否結束，回傳勝方或 None"""
        alive = self.alive_players
        wolves = [p for p in alive if not p.is_good]
        gods = [p for p in alive if p.faction == "god"]
        villagers = [p for p in alive if p.faction == "villager"]

        if len(wolves) == 0:
            return "好人陣營"
        if len(gods) == 0 or len(villagers) == 0:
            return "狼人陣營"
        return None

    async def _ai_action(self, player: SimulatedPlayer, context: str,
                         valid_targets: list[int], action_type: str) -> Optional[int]:
        """呼叫 AI 取得行動"""
        resp = await self.ai.get_ai_action(
            player.role, context, valid_targets,
            speech_history=self.speech_history
        )
        raw = resp

        # 解析
        target_id = None
        is_legal = True
        if str(resp).strip().lower() != "no":
            try:
                target_id = int(resp)
                if target_id not in valid_targets:
                    is_legal = False
            except (ValueError, TypeError):
                is_legal = False
                target_id = None

        # 角色意識檢查
        is_role_aware = True
        violation = ""
        if target_id is not None:
            if action_type == "kill" and player.role in WOLF_FACTION:
                target_p = self.get_player(target_id)
                if target_p and not target_p.is_good:
                    is_role_aware = False
                    violation = "狼人自刀同伴"
            elif action_type == "check" and target_id == player.id:
                is_role_aware = False
                violation = "預言家查驗自己"
            elif action_type == "guard":
                if target_id == self.last_guard_target:
                    is_role_aware = False
                    violation = "守衛連續守同一人"

        record = ActionRecord(
            player_id=player.id, role=player.role,
            action_type=action_type, target_id=target_id,
            valid_targets=valid_targets, raw_response=str(raw),
            is_legal=is_legal, is_role_aware=is_role_aware,
            violation_note=violation
        )
        self.result.actions.append(record)

        if not is_legal:
            self._log(f"    {C.RED}⚠ {player.role} ({player.id}號) 回傳了非法目標: {raw}{C.RESET}")
            return None

        return target_id

    # ─── 夜晚 ──────────────────────────────────────────────

    async def run_night(self) -> list[SimulatedPlayer]:
        """執行夜晚階段，回傳死亡玩家列表"""
        self._log(f"\n{C.BOLD}{C.BLUE}  🌙 天黑了 (第 {self.day_count + 1} 天夜晚){C.RESET}")

        alive = self.alive_players
        alive_ids = self.alive_ids
        context_base = f"夜晚行動。場上存活 {len(alive)} 人。存活玩家編號: {alive_ids}。"

        # 守衛
        guard_protect = None
        guards = [p for p in alive if p.role == "守衛"]
        if guards:
            guard = guards[0]
            targets = [pid for pid in alive_ids if pid != self.last_guard_target]
            if targets:
                guard_protect = await self._ai_action(
                    guard, context_base + " 你要守護誰？",
                    targets, "guard"
                )
                if guard_protect is not None:
                    self._log(f"    🛡️ 守衛守護了 {guard_protect} 號")
                    self.last_guard_target = guard_protect
                else:
                    self._log(f"    🛡️ 守衛空守")
                    self.last_guard_target = None

        # 狼人
        wolf_kill = None
        wolves = [p for p in alive if p.role in WOLF_FACTION]
        if wolves:
            wolf_votes = []
            non_wolf_ids = [p.id for p in alive if p.is_good]
            targets = non_wolf_ids if non_wolf_ids else alive_ids
            for wolf in wolves:
                kill_target = await self._ai_action(
                    wolf, context_base + f" 你的狼隊友: {[w.id for w in wolves if w != wolf]}。你要殺誰？",
                    targets, "kill"
                )
                if kill_target is not None:
                    wolf_votes.append(kill_target)

            if wolf_votes:
                from collections import Counter
                counts = Counter(wolf_votes)
                max_v = counts.most_common(1)[0][1]
                candidates = [k for k, v in counts.items() if v == max_v]
                wolf_kill = random.choice(candidates)
                self._log(f"    🐺 狼人決定殺 {wolf_kill} 號")

        # 預言家
        seers = [p for p in alive if p.role == "預言家"]
        if seers:
            seer = seers[0]
            check_targets = [pid for pid in alive_ids if pid != seer.id]
            check_id = await self._ai_action(
                seer, context_base + " 你要查驗誰？",
                check_targets, "check"
            )
            if check_id is not None:
                target_p = self.get_player(check_id)
                if target_p:
                    is_wolf = not target_p.is_good
                    result_str = "狼人 🐺" if is_wolf else "好人 ✅"
                    self._log(f"    🔮 預言家查驗 {check_id} 號 → {result_str}")

        # 女巫
        witch_save = False
        witch_poison_id = None
        witches = [p for p in alive if p.role == "女巫"]
        if witches:
            witch = witches[0]
            # 解藥
            if self.witch_potions['antidote'] and wolf_kill is not None:
                # AI 簡單邏輯: 第一晚救人
                if self.day_count == 0:
                    witch_save = True
                    self.witch_potions['antidote'] = False
                    self._log(f"    🧪 女巫使用解藥救了 {wolf_kill} 號")

            # 毒藥
            if self.witch_potions['poison'] and not witch_save:
                poison_targets = [pid for pid in alive_ids if pid != witch.id]
                poison_id = await self._ai_action(
                    witch, context_base + " 你要對誰使用毒藥？",
                    poison_targets, "poison"
                )
                if poison_id is not None:
                    witch_poison_id = poison_id
                    self.witch_potions['poison'] = False
                    self._log(f"    ☠️ 女巫毒了 {poison_id} 號")

        # 結算死亡
        dead_ids = set()
        if wolf_kill and not (wolf_kill == guard_protect) and not witch_save:
            dead_ids.add(wolf_kill)
        if witch_poison_id:
            dead_ids.add(witch_poison_id)

        dead_players = []
        for did in dead_ids:
            p = self.kill_player(did)
            if p:
                dead_players.append(p)

        return dead_players

    # ─── 白天發言 ──────────────────────────────────────────

    async def run_day(self, dead_players: list[SimulatedPlayer]):
        """白天發言階段"""
        self.day_count += 1
        self.speech_history = []
        dead_info = ", ".join([f"{p.name}({p.id}號)" for p in dead_players]) if dead_players else "無"
        self.last_dead_names = [p.name for p in dead_players]

        self._log(f"\n{C.BOLD}{C.YELLOW}  🌞 第 {self.day_count} 天白天{C.RESET}")
        if dead_players:
            self._log(f"    💀 昨晚死亡: {dead_info}")
        else:
            self._log(f"    ✨ 昨晚是平安夜")

        # 隨機發言順序
        speakers = list(self.alive_players)
        random.shuffle(speakers)

        self._log(f"\n    {C.DIM}--- 發言階段 ---{C.RESET}")

        for i, player in enumerate(speakers):
            is_first = (i == 0)
            context = f"現在是第 {self.day_count} 天白天。存活玩家: {len(self.alive_players)} 人。昨晚死亡名單：{dead_info}。"

            speech = await self.ai.get_ai_speech(
                player.id, player.role, context,
                speech_history=self.speech_history if not is_first else None
            )

            if not speech:
                speech = ""

            # 紀錄
            char_count = len(speech)
            is_empty = char_count < 5
            quality_ok = 30 <= char_count <= 300  # 寬鬆範圍

            # 幻覺檢測: 首位發言者引用前人
            has_hallucination = False
            if is_first and speech:
                halluc_patterns = [
                    r"前面.{0,5}(說|提|講)",
                    r"同意.{0,5}(的|說法|觀點)",
                    r"\d+\s*號.{0,5}(說|提到|認為)",
                    r"剛才.{0,5}(有人|玩家)",
                    r"聽[到了].{0,5}(有人|玩家)",
                ]
                for pat in halluc_patterns:
                    if re.search(pat, speech):
                        has_hallucination = True
                        break

            record = SpeechRecord(
                player_id=player.id, role=player.role,
                speech=speech, is_first_speaker=is_first,
                char_count=char_count, is_empty=is_empty,
                has_hallucination=has_hallucination,
                quality_ok=quality_ok
            )
            self.result.speeches.append(record)

            # 加入發言歷史
            self.speech_history.append(f"{player.name}({player.id}號): {speech}")

            # 顯示發言摘要
            preview = speech[:80].replace('\n', ' ') + ("..." if len(speech) > 80 else "")
            faction_tag = C.RED + "[狼]" if not player.is_good else C.GREEN + "[好]"
            halluc_tag = f" {C.BG_RED}{C.WHITE} 幻覺! {C.RESET}" if has_hallucination else ""
            self._log(f"    {faction_tag}{C.RESET} {player.id}號 {player.role}: {C.DIM}{preview}{C.RESET}{halluc_tag}")

    # ─── 投票 ──────────────────────────────────────────────

    async def run_vote(self) -> Optional[SimulatedPlayer]:
        """投票階段，回傳被處決的玩家"""
        self._log(f"\n    {C.DIM}--- 投票階段 ---{C.RESET}")

        alive = self.alive_players
        alive_ids = self.alive_ids
        vote_counts: dict[int, int] = {}

        for voter in alive:
            context = f"第 {self.day_count} 天白天投票階段。場上存活 {len(alive)} 人。存活玩家編號: {alive_ids}。"
            targets = [pid for pid in alive_ids if pid != voter.id]

            resp = await self.ai.get_ai_action(
                voter.role, context, targets,
                speech_history=self.speech_history
            )

            target_id = None
            is_abstain = str(resp).strip().lower() == "no"

            if not is_abstain:
                try:
                    target_id = int(resp)
                    if target_id not in targets:
                        target_id = None
                except (ValueError, TypeError):
                    target_id = None

            # 紀錄
            target_role = None
            is_correct = True
            if target_id is not None:
                target_p = self.get_player(target_id)
                target_role = target_p.role if target_p else None

                # 判斷投票正確性
                if voter.is_good:
                    # 好人投狼人 = 正確
                    is_correct = target_p is not None and not target_p.is_good
                else:
                    # 狼人投好人 = 正確
                    is_correct = target_p is not None and target_p.is_good

                vote_counts[target_id] = vote_counts.get(target_id, 0) + 1
            else:
                is_correct = False  # 棄票不算正確

            self.result.votes.append(VoteRecord(
                voter_id=voter.id, voter_role=voter.role,
                target_id=target_id, target_role=target_role,
                is_correct=is_correct
            ))

            vote_tag = f"→ {target_id}號" if target_id else "棄票"
            correct_tag = C.GREEN + "✓" if is_correct else C.RED + "✗"
            self._log(f"    {voter.id}號 {voter.role} {vote_tag} {correct_tag}{C.RESET}")

        # 結算
        if not vote_counts:
            self._log(f"    所有人棄票，無人被處決。")
            return None

        max_votes = max(vote_counts.values())
        candidates = [pid for pid, v in vote_counts.items() if v == max_votes]

        if len(candidates) > 1:
            self._log(f"    ⚖️ 平票！無人被處決。")
            return None

        victim_id = candidates[0]
        victim = self.kill_player(victim_id)
        if victim:
            self._log(f"    ⚔️ {victim.name} ({victim.role}) 以 {max_votes} 票被處決！")
        return victim

    # ─── 完整遊戲 ──────────────────────────────────────────

    async def run_full_game(self) -> GameResult:
        """執行完整遊戲"""
        self.setup()

        for _ in range(MAX_DAYS):
            # 夜晚
            dead = await self.run_night()

            # 檢查是否結束
            winner = self.check_game_over()
            if winner:
                self.result.winner = winner
                self.result.day_count = self.day_count + 1
                self._log(f"\n{C.BOLD}{C.MAGENTA}  🏆 遊戲結束！{winner}獲勝！ (第 {self.result.day_count} 天){C.RESET}")
                return self.result

            # 白天
            await self.run_day(dead)

            # 檢查（白天不會有死亡，但以防萬一）
            winner = self.check_game_over()
            if winner:
                self.result.winner = winner
                self.result.day_count = self.day_count
                self._log(f"\n{C.BOLD}{C.MAGENTA}  🏆 遊戲結束！{winner}獲勝！ (第 {self.result.day_count} 天){C.RESET}")
                return self.result

            # 投票
            await self.run_vote()

            # 檢查
            winner = self.check_game_over()
            if winner:
                self.result.winner = winner
                self.result.day_count = self.day_count
                self._log(f"\n{C.BOLD}{C.MAGENTA}  🏆 遊戲結束！{winner}獲勝！ (第 {self.result.day_count} 天){C.RESET}")
                return self.result

        self._log(f"\n{C.YELLOW}  ⏰ 遊戲超時 ({MAX_DAYS} 天)，強制結束。{C.RESET}")
        self.result.winner = "平局"
        self.result.day_count = MAX_DAYS
        return self.result


# ═══════════════════════════════════════════════════════════════
# 評分系統
# ═══════════════════════════════════════════════════════════════

class AIScorer:
    """AI 智商評分系統"""

    @staticmethod
    def score_action_legality(results: list[GameResult]) -> float:
        """行動合法性: AI 回傳的目標是否在可選範圍內"""
        total = 0
        legal = 0
        for r in results:
            for a in r.actions:
                total += 1
                if a.is_legal:
                    legal += 1
        return (legal / total * 100) if total > 0 else 100.0

    @staticmethod
    def score_role_awareness(results: list[GameResult]) -> float:
        """角色意識: 是否犯角色錯誤 (自刀/查自己/連守)"""
        total = 0
        aware = 0
        for r in results:
            for a in r.actions:
                total += 1
                if a.is_role_aware:
                    aware += 1
        return (aware / total * 100) if total > 0 else 100.0

    @staticmethod
    def score_speech_quality(results: list[GameResult]) -> float:
        """發言品質: 字數合格且非空白"""
        total = 0
        good = 0
        for r in results:
            for s in r.speeches:
                total += 1
                if s.quality_ok and not s.is_empty:
                    good += 1
        return (good / total * 100) if total > 0 else 100.0

    @staticmethod
    def score_anti_hallucination(results: list[GameResult]) -> float:
        """反幻覺: 首位發言者不應引用前人"""
        first_speeches = 0
        hallucinations = 0
        for r in results:
            for s in r.speeches:
                if s.is_first_speaker:
                    first_speeches += 1
                    if s.has_hallucination:
                        hallucinations += 1
        if first_speeches == 0:
            return 100.0
        # 每次幻覺扣 25 分
        penalty = hallucinations * 25
        return max(0, 100 - penalty)

    @staticmethod
    def score_vote_logic(results: list[GameResult]) -> float:
        """投票邏輯: 是否投向正確陣營"""
        total = 0
        correct = 0
        for r in results:
            for v in r.votes:
                if v.target_id is not None:
                    total += 1
                    if v.is_correct:
                        correct += 1
        return (correct / total * 100) if total > 0 else 50.0

    @staticmethod
    def calculate_iq(scores: dict[str, float]) -> int:
        """將五維分數轉換為 IQ 值 (目標: 70-130 範圍)"""
        weights = {
            "action_legality": 0.20,
            "role_awareness": 0.20,
            "speech_quality": 0.15,
            "anti_hallucination": 0.20,
            "vote_logic": 0.25,
        }
        weighted_avg = sum(scores[k] * weights[k] for k in weights)
        # 映射到 IQ: 0%→55, 50%→85, 75%→100, 100%→130
        iq = 55 + (weighted_avg / 100) * 75
        return int(round(iq))


# ═══════════════════════════════════════════════════════════════
# 報告產出
# ═══════════════════════════════════════════════════════════════

def print_report(results: list[GameResult], scores: dict[str, float], iq: int, elapsed: float):
    """印出彩色報告"""
    print(f"\n{'='*60}")
    print(f"{C.BOLD}{C.CYAN}  🧠 AI 智商測試報告 (AI IQ Benchmark Report){C.RESET}")
    print(f"{'='*60}")

    print(f"\n{C.BOLD}📊 遊戲統計{C.RESET}")
    print(f"  ├ 模擬局數: {len(results)}")
    print(f"  ├ 總耗時: {elapsed:.1f} 秒")
    for i, r in enumerate(results):
        winner_color = C.GREEN if "好人" in r.winner else C.RED if "狼人" in r.winner else C.YELLOW
        print(f"  ├ 第 {i+1} 局: {winner_color}{r.winner}{C.RESET} (第 {r.day_count} 天結束)")
    total_actions = sum(len(r.actions) for r in results)
    total_speeches = sum(len(r.speeches) for r in results)
    total_votes = sum(len(r.votes) for r in results)
    print(f"  └ 總計: {total_actions} 次行動, {total_speeches} 次發言, {total_votes} 次投票")

    print(f"\n{C.BOLD}📈 五維評分 (0-100){C.RESET}")

    dimension_names = {
        "action_legality": ("🎯 行動合法性", "AI 目標是否在合法範圍"),
        "role_awareness": ("🧩 角色意識  ", "有無自刀/查自己等錯誤"),
        "speech_quality": ("💬 發言品質  ", "字數合格且內容充實"),
        "anti_hallucination": ("🚫 反幻覺    ", "首位發言不編造前人話語"),
        "vote_logic": ("🗳️ 投票邏輯  ", "好人投狼/狼人投好人"),
    }

    for key, (name, desc) in dimension_names.items():
        score = scores[key]
        # 顏色
        if score >= 80:
            color = C.GREEN
            grade = "優秀"
        elif score >= 60:
            color = C.YELLOW
            grade = "尚可"
        elif score >= 40:
            color = C.RED
            grade = "偏弱"
        else:
            color = C.BG_RED + C.WHITE
            grade = "危險"

        # 進度條
        bar_len = 30
        filled = int(score / 100 * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)

        print(f"  {name}  {color}{bar} {score:5.1f}% ({grade}){C.RESET}")
        print(f"  {C.DIM}               {desc}{C.RESET}")

    # IQ 等級
    print(f"\n{'─'*60}")
    if iq >= 120:
        iq_color = C.GREEN
        iq_label = "天才級 🌟"
    elif iq >= 105:
        iq_color = C.GREEN
        iq_label = "聰明 💡"
    elif iq >= 90:
        iq_color = C.YELLOW
        iq_label = "平均水準 📊"
    elif iq >= 75:
        iq_color = C.RED
        iq_label = "需要加強 📉"
    else:
        iq_color = C.BG_RED + C.WHITE
        iq_label = "嚴重不足 🚨"

    print(f"  {C.BOLD}🧠 AI 智商 (IQ): {iq_color}{iq}{C.RESET} {iq_color}{iq_label}{C.RESET}")
    print(f"{'─'*60}")

    # 詳細問題
    issues = []
    for r in results:
        for a in r.actions:
            if not a.is_legal:
                issues.append(f"  ⚠ 非法行動: {a.role}({a.player_id}號) {a.action_type} → 回傳 '{a.raw_response}'，可選: {a.valid_targets}")
            if not a.is_role_aware and a.violation_note:
                issues.append(f"  ⚠ 角色錯誤: {a.violation_note} ({a.role} {a.player_id}號)")
        for s in r.speeches:
            if s.has_hallucination:
                preview = s.speech[:60].replace('\n', ' ')
                issues.append(f"  👻 幻覺: {s.role}({s.player_id}號) 首位發言卻引用前人: '{preview}...'")
            if s.is_empty:
                issues.append(f"  🔇 空白發言: {s.role}({s.player_id}號)")

    if issues:
        print(f"\n{C.BOLD}{C.RED}⚠ 發現的問題 ({len(issues)} 項){C.RESET}")
        for issue in issues[:20]:  # 最多顯示 20 條
            print(issue)
        if len(issues) > 20:
            print(f"  ... 還有 {len(issues) - 20} 項")
    else:
        print(f"\n{C.GREEN}✅ 未發現明顯問題！{C.RESET}")

    print(f"\n{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# 主程式
# ═══════════════════════════════════════════════════════════════

async def check_ollama_connection(ai: AIManager) -> bool:
    """測試 Ollama 連線"""
    print(f"{C.DIM}正在檢查 Ollama 連線 ({ai.ollama_host})...{C.RESET}")
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ai.ollama_host}/api/tags", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = [m['name'] for m in data.get('models', [])]
                    print(f"{C.GREEN}✅ Ollama 連線成功！可用模型: {', '.join(models[:5])}{C.RESET}")
                    if ai.ollama_model not in models and not any(ai.ollama_model in m for m in models):
                        print(f"{C.YELLOW}⚠ 模型 '{ai.ollama_model}' 可能不在已安裝列表中，但仍會嘗試使用。{C.RESET}")
                    return True
                else:
                    print(f"{C.RED}❌ Ollama 回應異常: HTTP {resp.status}{C.RESET}")
                    return False
    except Exception as e:
        print(f"{C.RED}❌ 無法連線到 Ollama: {e}{C.RESET}")
        print(f"{C.YELLOW}請確認 Ollama 正在執行: ollama serve{C.RESET}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="AI 智商測試程式 (Werewolf AI IQ Benchmark)")
    parser.add_argument("--games", type=int, default=3, help="模擬局數 (預設: 3)")
    parser.add_argument("--players", type=int, default=9, help="玩家人數 (目前僅支援 9)")
    parser.add_argument("--model", type=str, help="指定 Ollama 模型 (預設: env OLLAMA_MODEL 或 gpt-oss:20b)")
    parser.add_argument("--quiet", action="store_true", help="安靜模式 (只顯示最終報告)")
    args = parser.parse_args()

    model_name = args.model or os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')

    print(f"\n{C.BOLD}{C.CYAN}{'═'*60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  🧠 AI 智商測試程式 — 狼人殺 AI IQ Benchmark{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'═'*60}{C.RESET}")
    print(f"  模型: {model_name}")
    print(f"  模擬局數: {args.games}")
    print(f"  配置: 9人局 (3狼 + 預女獵 + 3平民)\n")

    ai = AIManager(ollama_model=args.model)

    # 連線檢查
    if ai.provider == 'ollama':
        ok = await check_ollama_connection(ai)
        if not ok:
            print(f"\n{C.RED}測試中止。{C.RESET}")
            return

    results: list[GameResult] = []
    start_time = time.time()

    try:
        for i in range(args.games):
            print(f"\n{C.BOLD}{'━'*60}{C.RESET}")
            print(f"{C.BOLD}  📋 開始第 {i+1}/{args.games} 局模擬{C.RESET}")
            print(f"{'━'*60}")

            sim = GameSimulator(ai, verbose=not args.quiet)
            result = await sim.run_full_game()
            results.append(result)

    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}⚠ 使用者中斷。將根據已完成的 {len(results)} 局產出報告。{C.RESET}")
    finally:
        await ai.close()

    elapsed = time.time() - start_time

    if not results:
        print(f"{C.RED}沒有完成任何一局遊戲。{C.RESET}")
        return

    # 評分
    scorer = AIScorer()
    scores = {
        "action_legality": scorer.score_action_legality(results),
        "role_awareness": scorer.score_role_awareness(results),
        "speech_quality": scorer.score_speech_quality(results),
        "anti_hallucination": scorer.score_anti_hallucination(results),
        "vote_logic": scorer.score_vote_logic(results),
    }
    iq = scorer.calculate_iq(scores)

    # 報告
    print_report(results, scores, iq, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
