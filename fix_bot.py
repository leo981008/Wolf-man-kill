import re

with open("src/bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# Fix next_phase bug
next_pattern = re.compile(r"elif game\.phase == GamePhase\.DAY:\n\s*if not engine\.votes:\n\s*await engine\.start_voting\(\)\n\s*await interaction\.followup\.send\(\"進入投票階段。\"\)\n\s*else:\n\s*await engine\.resolve_votes\(\)\n\s*await interaction\.followup\.send\(\"結算投票。\"\)")
next_replace = """elif game.phase == GamePhase.DAY:
        if not getattr(engine, 'voting_started', False):
            await engine.start_voting()
            await interaction.followup.send("進入投票階段。")
        else:
            await engine.resolve_votes()
            await interaction.followup.send("結算投票。")"""
code = next_pattern.sub(next_replace, code)

with open("src/bot.py", "w", encoding="utf-8") as f:
    f.write(code)
