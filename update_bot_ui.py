import re

with open("src/bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# Modify imports
if "from discord.ui import View, Button" not in code:
    code = code.replace("from discord import app_commands", "from discord import app_commands\nfrom discord.ui import View, Button, Select")

# Create Views
views_code = """

class ActionSelect(discord.ui.Select):
    def __init__(self, options, placeholder, custom_id):
        super().__init__(placeholder=placeholder, options=options, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        # We handle this in the main View callback to coordinate
        pass

class ActionView(discord.ui.View):
    def __init__(self, engine, player, game, is_witch=False):
        super().__init__(timeout=120)
        self.engine = engine
        self.player = player
        self.game = game
        self.is_witch = is_witch
        self.target1 = 0
        self.target2 = 0

        options = [discord.SelectOption(label="不使用/跳過", value="0")]
        for n in game.get_alive_numbers():
            options.append(discord.SelectOption(label=f"{n}號", value=str(n)))

        if is_witch:
            self.heal_select = ActionSelect(options, "選擇拯救目標 (可選)", "heal")
            self.poison_select = ActionSelect(options, "選擇毒殺目標 (可選)", "poison")
            self.add_item(self.heal_select)
            self.add_item(self.poison_select)
        else:
            self.target_select = ActionSelect(options, "選擇目標", "target")
            self.add_item(self.target_select)

    @discord.ui.button(label="確認行動", style=discord.ButtonStyle.primary, row=2)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_witch:
            self.target1 = int(self.heal_select.values[0]) if self.heal_select.values else 0
            self.target2 = int(self.poison_select.values[0]) if self.poison_select.values else 0
            self.engine.night_actions_cache[self.player.number] = (self.target1, self.target2)
            await interaction.response.send_message(f"你選擇了 救:{self.target1} 毒:{self.target2}。", ephemeral=True)
        else:
            self.target1 = int(self.target_select.values[0]) if self.target_select.values else 0
            self.engine.night_actions_cache[self.player.number] = self.target1
            await interaction.response.send_message(f"你選擇了 {self.target1} 號作為目標。", ephemeral=True)
        self.stop()

class VoteView(discord.ui.View):
    def __init__(self, engine, player, game):
        super().__init__(timeout=120)
        self.engine = engine
        self.player = player
        self.game = game

        options = [discord.SelectOption(label="棄票", value="0")]
        for n in game.get_alive_numbers():
            options.append(discord.SelectOption(label=f"{n}號", value=str(n)))

        self.vote_select = ActionSelect(options, "選擇投票目標", "vote")
        self.add_item(self.vote_select)

    @discord.ui.button(label="確認投票", style=discord.ButtonStyle.primary, row=1)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        target = int(self.vote_select.values[0]) if self.vote_select.values else 0
        self.engine.votes[self.player.number] = target
        await interaction.response.send_message(f"你投票給了 {target} 號。", ephemeral=True)
        self.stop()
"""

if "class ActionSelect" not in code:
    code = code.replace("class WolfBot", views_code + "\nclass WolfBot")

# Update /action command
action_pattern = re.compile(r'@bot\.tree\.command\(name="action", description="夜晚行動"\)\nasync def night_action\(interaction: discord\.Interaction, target1: int, target2: int = 0\):.*?else:\n.*?await interaction\.response\.send_message\(f"你選擇了 \{target1\} 號作為目標。", ephemeral=True\)', re.DOTALL)

new_action = """@bot.tree.command(name="action", description="夜晚行動 (開啟按鈕介面)")
async def night_action(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id not in bot.engines:
        await interaction.response.send_message("沒有進行中的遊戲。", ephemeral=True)
        return

    game = bot.games[channel_id]
    engine = bot.engines[channel_id]

    if game.phase not in [GamePhase.NIGHT, GamePhase.NIGHT_WITCH_PHASE]:
        await interaction.response.send_message("現在不是夜晚行動時間。", ephemeral=True)
        return

    player = next((p for p in game.players.values() if p.user.id == interaction.user.id), None)

    if not player or not player.is_alive:
        await interaction.response.send_message("你不能行動。", ephemeral=True)
        return

    if game.phase == GamePhase.NIGHT_WITCH_PHASE and player.role.name != "女巫":
        await interaction.response.send_message("現在是女巫行動時間。", ephemeral=True)
        return

    if game.phase == GamePhase.NIGHT and player.role.name == "女巫":
        await interaction.response.send_message("女巫請在稍後的單獨階段行動。", ephemeral=True)
        return

    is_witch = player.role.name == "女巫"
    view = ActionView(engine, player, game, is_witch)
    await interaction.response.send_message("請選擇你的行動目標：", view=view, ephemeral=True)"""

code = action_pattern.sub(new_action, code)

# Update /vote command
vote_pattern = re.compile(r'@bot\.tree\.command\(name="vote", description="白天投票"\)\nasync def vote\(interaction: discord\.Interaction, target: int\):.*?engine\.votes\[voter\.number\] = target\n\s*await interaction\.response\.send_message\(f"你投票給了 \{target\} 號。", ephemeral=True\)', re.DOTALL)

new_vote = """@bot.tree.command(name="vote", description="白天投票 (開啟按鈕介面)")
async def vote(interaction: discord.Interaction):
    channel_id = interaction.channel_id
    if channel_id not in bot.engines:
        await interaction.response.send_message("沒有進行中的遊戲。", ephemeral=True)
        return

    game = bot.games[channel_id]
    engine = bot.engines[channel_id]

    if game.phase != GamePhase.DAY:
        await interaction.response.send_message("現在不是投票時間。", ephemeral=True)
        return

    voter = next((p for p in game.players.values() if p.user.id == interaction.user.id), None)

    if not voter or not voter.is_alive:
        await interaction.response.send_message("你不能投票。", ephemeral=True)
        return

    view = VoteView(engine, voter, game)
    await interaction.response.send_message("請選擇你要投票的目標：", view=view, ephemeral=True)"""

code = vote_pattern.sub(new_vote, code)

with open("src/bot.py", "w", encoding="utf-8") as f:
    f.write(code)
print("Updated bot.py with UI views")
