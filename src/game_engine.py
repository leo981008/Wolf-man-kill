import asyncio
import random
import re
from collections import Counter
from typing import Dict, List, Optional
import discord
from src.game_models import GameState, GamePhase, Player, Faction, ROLE_MAPPING, Witch, Guard, Hunter, Seer, Idiot
from src.ai_manager import AIManager
from src.utils import logger, safe_send, gather_safe_sends, generate_number_image_file

class GameEngine:
    def __init__(self, game_state: GameState, ai_manager: AIManager):
        self.game = game_state
        self.ai = ai_manager
        self.votes: Dict[int, int] = {}
        self.night_actions_cache: Dict[int, int] = {}
        self.voting_started = False
        self.pending_hunter = None

    async def distribute_roles(self, roles_dict: Dict[str, int]):
        role_list = []
        for role_name, count in roles_dict.items():
            role_list.extend([role_name] * count)

        random.shuffle(role_list)
        self.game.wolf_count = 0
        self.game.god_count = 0
        self.game.villager_count = 0

        dm_tasks = []
        for i, player in enumerate(self.game.players.values()):
            if i < len(role_list):
                role_name = role_list[i]
                role_class = ROLE_MAPPING.get(role_name)
                if role_class:
                    player.role = role_class()
                    if player.role.faction == Faction.WOLF:
                        self.game.wolf_count += 1
                    elif player.role.faction == Faction.GOD:
                        self.game.god_count += 1
                    elif player.role.faction == Faction.VILLAGER:
                        self.game.villager_count += 1

                if player.is_ai:
                    player.ai_memory.append(f"我的身分是 {role_name}。")
                else:
                    async def send_role_dm(p: Player, r_name: str):
                        try:
                            file = generate_number_image_file(p.number)
                            embed = discord.Embed(title="狼人殺角色分配", description=f"你的編號是 **{p.number}** 號\n你的身分是 **{r_name}**", color=0x2b2d31)
                            await p.user.send(embed=embed, file=file)
                        except Exception as e:
                            logger.error(f"Failed to send role DM to {p.user}: {e}")
                    dm_tasks.append(send_role_dm(player, role_name))
        if dm_tasks:
            await gather_safe_sends(dm_tasks)

    async def start_night(self):
        self.game.phase = GamePhase.NIGHT
        self.game.day_count += 1
        self.game.night_kills = []
        self.game.witch_heal = None
        self.game.witch_poison = None
        self.game.guard_protect = None
        self.night_actions_cache.clear()

        await safe_send(self.game.channel, f"**🌙 第 {self.game.day_count} 天夜晚降臨，請所有玩家閉眼。**\n狼人、預言家、守衛請行動。(人類玩家請使用 `/action 號碼`，完畢後房主使用 `/next`)")

        overwrite = discord.PermissionOverwrite(send_messages=False)
        try:
            await self.game.channel.set_permissions(self.game.channel.guild.default_role, overwrite=overwrite)
        except Exception:
            pass

        await self._process_ai_night_actions_phase1()

    async def _process_ai_night_actions_phase1(self):
        alive_players = self.game.get_alive_players()
        alive_numbers = self.game.get_alive_numbers()
        for player in alive_players:
            if player.is_ai and not isinstance(player.role, Witch) and player.role.faction != Faction.VILLAGER and player.role.faction != Faction.NONE:
                context = "\n".join(player.ai_memory) + f"\n存活玩家：{alive_numbers}。"
                action = await self.ai.generate_night_action(player.role.name, context, alive_numbers)
                if action:
                    target = action.get('target', 0)
                    if target == 0 or target in alive_numbers:
                        self.night_actions_cache[player.number] = target
                        if player.role.faction == Faction.WOLF:
                            if target != 0:
                                player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我提議刀 {target} 號。")
                        elif isinstance(player.role, Seer):
                            if target != 0:
                                player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我查驗了 {target} 號。")
                        elif isinstance(player.role, Guard):
                            player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我守護了 {target if target != 0 else '空'}。")

    async def resolve_night_phase1_and_start_witch(self):
        # Resolve wolf kill first
        wolf_votes = []
        for player_num, target in self.night_actions_cache.items():
            player = self.game.players.get(player_num)
            if player and player.is_alive and player.role.faction == Faction.WOLF:
                wolf_votes.append(target)

        if wolf_votes:
            most_common = Counter(wolf_votes).most_common(1)
            if most_common:
                self.game.night_kills.append(most_common[0][0])

        # Resolve Seer and Guard
        for player_num, target in list(self.night_actions_cache.items()):
            player = self.game.players.get(player_num)
            if not player or not player.is_alive:
                continue
            if isinstance(player.role, Guard):
                if target == 0:
                    player.role.last_guarded = 0
                elif getattr(player.role, 'last_guarded', None) != target:
                    self.game.guard_protect = target
                    player.role.last_guarded = target
            elif isinstance(player.role, Seer):
                target_player = self.game.players.get(target)
                if target_player:
                    faction_str = "壞人" if target_player.role.faction == Faction.WOLF else "好人"
                    msg = f"你查驗了 {target} 號玩家，他的陣營是：**{faction_str}**"
                    if not player.is_ai:
                        await safe_send(player.user, msg)
                    else:
                        player.ai_memory.append(f"結果：{target} 號是 {faction_str}。")

        self.game.phase = GamePhase.NIGHT_WITCH_PHASE
        self.night_actions_cache.clear() # Clear for witch
        await safe_send(self.game.channel, "**女巫請睜眼。**\n(人類女巫請使用 `/action 救人號碼 毒人號碼`，不使用填0，完畢後房主使用 `/next`)")

        # Process AI Witch
        alive_players = self.game.get_alive_players()
        alive_numbers = self.game.get_alive_numbers()
        for player in alive_players:
            if player.is_ai and isinstance(player.role, Witch):
                kill_target = self.game.night_kills[0] if self.game.night_kills else 0
                context = "\n".join(player.ai_memory) + f"\n存活玩家：{alive_numbers}。今晚倒牌的是 {kill_target} 號。\n解藥：{'可用' if player.role.has_heal else '已用'}。毒藥：{'可用' if player.role.has_poison else '已用'}。"
                action = await self.ai.generate_witch_action(context, alive_numbers)
                if action:
                    heal_target = action.get('heal_target', 0)
                    poison_target = action.get('poison_target', 0)

                    if heal_target != 0 and heal_target == kill_target and player.role.has_heal:
                        self.game.witch_heal = heal_target
                        player.role.has_heal = False
                        player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我救了 {heal_target} 號。")
                    if poison_target in alive_numbers and player.role.has_poison:
                        self.game.witch_poison = poison_target
                        player.role.has_poison = False
                        player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我毒了 {poison_target} 號。")

    async def resolve_night_final(self):
        # Process Human witch if any was cached in night_actions_cache
        # cache key is player_num, value is tuple (heal, poison)
        for player_num, targets in self.night_actions_cache.items():
            player = self.game.players.get(player_num)
            if player and player.is_alive and isinstance(player.role, Witch) and not player.is_ai:
                heal_target, poison_target = targets
                kill_target = self.game.night_kills[0] if self.game.night_kills else 0
                if heal_target != 0 and heal_target == kill_target and player.role.has_heal:
                    self.game.witch_heal = heal_target
                    player.role.has_heal = False
                if poison_target != 0 and player.role.has_poison:
                    self.game.witch_poison = poison_target
                    player.role.has_poison = False

        dead_tonight = set()

        for target in self.game.night_kills:
            if self.game.witch_heal != target and self.game.guard_protect != target:
                 dead_tonight.add(target)
            elif self.game.witch_heal == target and self.game.guard_protect == target:
                 dead_tonight.add(target) # 同守同救 = 死

        if self.game.witch_poison:
            dead_tonight.add(self.game.witch_poison)

        death_messages = []
        for p_num in dead_tonight:
            if p_num in self.game.players:
                player = self.game.players[p_num]
                player.is_alive = False
                if isinstance(player.role, Hunter) and p_num == self.game.witch_poison:
                    player.role.can_shoot = False
                if self.game.day_count == 1:
                     player.has_last_words = True
                death_messages.append(f"{p_num}號玩家")

        self.game.phase = GamePhase.DAY

        overwrite = discord.PermissionOverwrite(send_messages=True)
        try:
            await self.game.channel.set_permissions(self.game.channel.guild.default_role, overwrite=overwrite)
        except Exception:
            pass

        msg = f"**☀️ 第 {self.game.day_count} 天白天降臨。**\n"
        if death_messages:
             msg += f"昨晚死亡的是：{', '.join(death_messages)}。"
        else:
             msg += "昨晚是平安夜。"

        # Add to everyone's memory
        for p in self.game.players.values():
            if p.is_ai:
                p.ai_memory.append(f"第 {self.game.day_count} 天白天，系統宣布：{msg}")

        await safe_send(self.game.channel, msg)

        winner = self.game.check_game_over()
        if winner:
            await self._end_game(winner)
        else:
            await self.start_day()

    async def start_day(self):
        alive_numbers = self.game.get_alive_numbers()
        order = list(alive_numbers)
        random.shuffle(order)
        order_str = ' -> '.join([str(n) for n in order])

        msg = f"**發言階段開始**\n發言順序為：{order_str}\n(AI 玩家會自動發言。人類玩家請直接在頻道發言。發言完畢或進行投票請房主使用 `/next`)"
        await safe_send(self.game.channel, msg)

        for p in self.game.players.values():
            if p.is_ai:
                p.ai_memory.append(f"發言順序：{order_str}")

        await self._process_ai_day_speeches(order)

    async def _process_ai_day_speeches(self, order: List[int]):
        for p_num in order:
            player = self.game.players.get(p_num)
            if player and player.is_alive and player.is_ai:
                context = "\n".join(player.ai_memory[-10:]) + f"\n存活玩家：{self.game.get_alive_numbers()}。"
                history = "\n".join(self.game.speech_history[-15:])
                speech = await self.ai.generate_day_speech(player.role.name, player.number, context, history)
                if speech:
                    msg = f"**[AI {player.number}號]**: {speech}"
                    await safe_send(self.game.channel, msg)
                    self.game.speech_history.append(f"{player.number}號: {speech}")
                    player.ai_memory.append(f"我發表了言論：{speech}")
                await asyncio.sleep(2)

    async def start_voting(self):
        self.votes.clear()
        self.voting_started = True
        alive_numbers = self.game.get_alive_numbers()
        await safe_send(self.game.channel, f"**開始投票**\n存活玩家：{alive_numbers}\n(人類玩家請使用 `/vote 號碼` 投票，全數投完後房主使用 `/next`)")
        await self._process_ai_votes()

    async def _process_ai_votes(self):
        alive_players = self.game.get_alive_players()
        alive_numbers = self.game.get_alive_numbers()
        for player in alive_players:
            if player.is_ai:
                context = "\n".join(player.ai_memory[-5:]) + f"\n第 {self.game.day_count} 天投票。存活：{alive_numbers}。發言紀錄：\n" + "\n".join(self.game.speech_history[-10:])
                target = await self.ai.generate_vote(player.role.name, player.number, context, alive_numbers)
                if target is not None:
                    self.votes[player.number] = target
                    await safe_send(self.game.channel, f"AI {player.number}號 已投票。")
                    player.ai_memory.append(f"我投票給了 {target} 號。")

    async def resolve_votes(self):
        self.voting_started = False
        if not self.votes:
            await safe_send(self.game.channel, "無人投票，平安日。")
            await self.start_night()
            return

        vote_counts = {}
        for voter, target in self.votes.items():
            if target != 0:
                vote_counts[target] = vote_counts.get(target, 0) + 1

        if not vote_counts:
            await safe_send(self.game.channel, "全員棄票，平安日。")
            await self.start_night()
            return

        max_votes = max(vote_counts.values())
        pk_targets = [t for t, c in vote_counts.items() if c == max_votes]

        results_str = "\n".join([f"{v}號 -> {t}號" for v, t in self.votes.items()])
        await safe_send(self.game.channel, f"**投票結果：**\n{results_str}")

        for p in self.game.players.values():
            if p.is_ai:
                p.ai_memory.append(f"投票結果：\n{results_str}")

        if len(pk_targets) > 1:
            await safe_send(self.game.channel, f"平票！{pk_targets} 號玩家進入 PK (此版本直接算作無人出局平安日)。")
            await self.start_night()
        else:
            exiled = pk_targets[0]
            player = self.game.players[exiled]

            if isinstance(player.role, Idiot) and not player.role.revealed:
                player.role.revealed = True
                msg = f"**{exiled}號玩家** 被公投出局，但他是 **白痴**，翻牌免除放逐！"
                await safe_send(self.game.channel, msg)
                for p in self.game.players.values():
                    if p.is_ai:
                        p.ai_memory.append(msg)
                await self.start_night()
            else:
                player.is_alive = False
                player.has_last_words = True
                msg = f"**{exiled}號玩家** 被公投出局！"
                await safe_send(self.game.channel, msg)
                for p in self.game.players.values():
                    if p.is_ai:
                        p.ai_memory.append(msg)

                winner = self.game.check_game_over()
                if winner:
                    await self._end_game(winner)
                else:
                    await self.start_night()


    async def resolve_hunter_shoot(self, target: int):
        if not self.pending_hunter:
            return

        hunter_player = self.pending_hunter
        self.pending_hunter = None

        target_player = self.game.players.get(target)
        if target_player and target_player.is_alive and hunter_player.role.can_shoot:
            target_player.is_alive = False
            msg = f"**{hunter_player.number}號 (獵人)** 開槍帶走了 **{target}號**！"
            await safe_send(self.game.channel, msg)
            for p in self.game.players.values():
                if p.is_ai:
                    p.ai_memory.append(msg)

            winner = self.game.check_game_over()
            if winner:
                await self._end_game(winner)
                return
        else:
            await safe_send(self.game.channel, f"**{hunter_player.number}號 (獵人)** 放棄開槍或無效目標。")

        # Continue game
        if self.game.phase == GamePhase.DAY:
            await self.start_night()
        else:
            await self.start_day()

    async def _end_game(self, winner: Faction):
        self.game.phase = GamePhase.ENDED
        roles_str = "\n".join([f"{p.number}號: {p.role.name} ({'存活' if p.is_alive else '死亡'})" for p in self.game.players.values()])
        await safe_send(self.game.channel, f"🎉 遊戲結束！**{winner.value}** 獲得勝利！\n\n**角色分配：**\n{roles_str}")
