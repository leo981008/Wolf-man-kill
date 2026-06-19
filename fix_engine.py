import re

with open("src/game_engine.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add voting_started and pending_hunter to init
code = code.replace("self.night_actions_cache: Dict[int, int] = {}", "self.night_actions_cache: Dict[int, int] = {}\n        self.voting_started = False\n        self.pending_hunter = None")

# 2. Fix AI heal
code = code.replace("if heal_target == kill_target and player.role.has_heal:", "if heal_target != 0 and heal_target == kill_target and player.role.has_heal:")

# 3. Fix Human heal
code = code.replace("if heal_target == kill_target and player.role.has_heal:\n                    self.game.witch_heal = heal_target", "if heal_target != 0 and heal_target == kill_target and player.role.has_heal:\n                    self.game.witch_heal = heal_target")

# 4. Fix AI Guard last_guarded
guard_pattern = re.compile(r"if isinstance\(player\.role, Guard\):\n\s*if getattr\(player\.role, 'last_guarded', None\) != target:\n\s*self\.game\.guard_protect = target\n\s*player\.role\.last_guarded = target")
guard_replace = """if isinstance(player.role, Guard):
                if target == 0:
                    player.role.last_guarded = 0
                elif getattr(player.role, 'last_guarded', None) != target:
                    self.game.guard_protect = target
                    player.role.last_guarded = target"""
code = guard_pattern.sub(guard_replace, code)

# 5. Fix start_voting and resolve_votes
code = code.replace("async def start_voting(self):\n        self.votes.clear()", "async def start_voting(self):\n        self.votes.clear()\n        self.voting_started = True")
code = code.replace("async def resolve_votes(self):\n        if not self.votes:", "async def resolve_votes(self):\n        self.voting_started = False\n        if not self.votes:")

# 6. Fix AI night action target 0
action_pattern = re.compile(r"action = await self\.ai\.generate_night_action\(player\.role\.name, context, alive_numbers\)\n\s*if action:\n\s*target = action\.get\('target'\)\n\s*if target and target in alive_numbers:\n\s*self\.night_actions_cache\[player\.number\] = target\n\s*if player\.role\.faction == Faction\.WOLF:\n\s*player\.ai_memory\.append\(f\"第 \{self\.game\.day_count\} 天夜晚，我提議刀 \{target\} 號。\"\)\n\s*elif isinstance\(player\.role, Seer\):\n\s*player\.ai_memory\.append\(f\"第 \{self\.game\.day_count\} 天夜晚，我查驗了 \{target\} 號。\"\)\n\s*elif isinstance\(player\.role, Guard\):\n\s*player\.ai_memory\.append\(f\"第 \{self\.game\.day_count\} 天夜晚，我守護了 \{target\} 號。\"\)")
action_replace = """action = await self.ai.generate_night_action(player.role.name, context, alive_numbers)
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
                            player.ai_memory.append(f"第 {self.game.day_count} 天夜晚，我守護了 {target if target != 0 else '空'}。")"""
code = action_pattern.sub(action_replace, code)

# 7. Add Hunter shoot method
hunter_code = """
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
"""
if "async def resolve_hunter_shoot" not in code:
    code = code.replace("async def _end_game(self, winner: Faction):", hunter_code + "\n    async def _end_game(self, winner: Faction):")

with open("src/game_engine.py", "w", encoding="utf-8") as f:
    f.write(code)
