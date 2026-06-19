import discord
from discord.ui import View, Button, Select
from src.game_models import Faction

class PlayerActionButton(Button):
    def __init__(self, target_num, label, custom_id, callback_func):
        super().__init__(style=discord.ButtonStyle.primary, label=label, custom_id=custom_id)
        self.target_num = target_num
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.target_num, self.view)

class ActionButtonsView(View):
    def __init__(self, engine, player, game, completion_event):
        super().__init__(timeout=60)
        self.engine = engine
        self.player = player
        self.game = game
        self.completion_event = completion_event

        alive_numbers = game.get_alive_numbers()

        try:
            # Add a skip button
            self.add_item(PlayerActionButton(0, "不行動", "action_0", self.handle_action))

            for n in alive_numbers:
                self.add_item(PlayerActionButton(n, f"{n}號", f"action_{n}", self.handle_action))
        except Exception:
            pass

    async def handle_action(self, interaction: discord.Interaction, target: int, view: View):
        self.engine.night_actions_cache[self.player.number] = target
        action_text = f"你選擇了 {target} 號作為目標。" if target != 0 else "你選擇了不行動。"
        await interaction.response.send_message(action_text, ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop()
        self.engine.human_actions_completed += 1
        if self.engine.human_actions_completed >= self.engine.expected_human_actions:
            self.completion_event.set()

class ActionSelect(discord.ui.Select):
    def __init__(self, options, placeholder, custom_id):
        super().__init__(placeholder=placeholder, options=options, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        pass # Handled in View

class WitchActionSelectView(View):
    def __init__(self, engine, player, game, completion_event):
        super().__init__(timeout=60)
        self.engine = engine
        self.player = player
        self.game = game
        self.completion_event = completion_event
        self.target1 = 0
        self.target2 = 0

        options = [discord.SelectOption(label="不使用/跳過", value="0")]
        for n in game.get_alive_numbers():
            options.append(discord.SelectOption(label=f"{n}號", value=str(n)))

        self.heal_select = ActionSelect(options, "選擇拯救目標 (可選)", "heal")
        self.poison_select = ActionSelect(options, "選擇毒殺目標 (可選)", "poison")
        try:
            self.add_item(self.heal_select)
            self.add_item(self.poison_select)
        except Exception:
            pass

    @discord.ui.button(label="確認行動", style=discord.ButtonStyle.primary, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.target1 = int(self.heal_select.values[0]) if self.heal_select.values else 0
        self.target2 = int(self.poison_select.values[0]) if self.poison_select.values else 0
        self.engine.night_actions_cache[self.player.number] = (self.target1, self.target2)
        await interaction.response.send_message(f"你選擇了 救:{self.target1} 毒:{self.target2}。", ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop()
        self.completion_event.set()

class VoteButtonsView(View):
    def __init__(self, engine, player, game, completion_event):
        super().__init__(timeout=60)
        self.engine = engine
        self.player = player
        self.game = game
        self.completion_event = completion_event

        alive_numbers = game.get_alive_numbers()

        try:
            self.add_item(PlayerActionButton(0, "棄票", "vote_0", self.handle_vote))

            for n in alive_numbers:
                self.add_item(PlayerActionButton(n, f"{n}號", f"vote_{n}", self.handle_vote))
        except Exception:
            pass

    async def handle_vote(self, interaction: discord.Interaction, target: int, view: View):
        self.engine.votes[self.player.number] = target
        vote_text = f"你投票給了 {target} 號。" if target != 0 else "你選擇了棄票。"
        await interaction.response.send_message(vote_text, ephemeral=True)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop()
        self.engine.human_votes_completed += 1
        if self.engine.human_votes_completed >= self.engine.expected_human_votes:
            self.completion_event.set()

class EndSpeechView(View):
    def __init__(self, completion_event, expected_user_id):
        super().__init__(timeout=60)
        self.completion_event = completion_event
        self.expected_user_id = expected_user_id

    @discord.ui.button(label="結束發言", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.expected_user_id:
            await interaction.response.send_message("現在不是你的發言時間！", ephemeral=True)
            return

        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        self.stop()
        self.completion_event.set()
