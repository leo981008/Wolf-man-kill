import sys
import os

print("Starting verification...")

try:
    print("Importing game_data...")
    import game_data
    print("game_data imported successfully.")
except Exception as e:
    print(f"Failed to import game_data: {e}")
    sys.exit(1)

try:
    print("Importing game_objects...")
    import game_objects
    print("game_objects imported successfully.")
except Exception as e:
    print(f"Failed to import game_objects: {e}")
    sys.exit(1)

try:
    print("Importing ai_manager...")
    import ai_manager
    print("ai_manager imported successfully.")
except Exception as e:
    print(f"Failed to import ai_manager: {e}")
    sys.exit(1)

try:
    print("Importing bot (this might fail if discord token is missing or if it tries to connect, but we just check syntax)...")
    # bot.py runs bot.run() if __name__ == "__main__", so importing it as a module is safe IF it doesn't have side effects on import.
    # checking bot.py content...
    # it creates `bot = WerewolfBot()`.
    # it calls `load_dotenv()`.
    import bot
    print("bot imported successfully.")
except Exception as e:
    print(f"Failed to import bot: {e}")
    # bot import might fail due to missing env vars or discord connection, which is expected in this environment
    # but SyntaxError would act differently.
    if isinstance(e, SyntaxError):
        sys.exit(1)

print("Verification complete. No syntax errors found in main modules.")
