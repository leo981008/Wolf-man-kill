import sys
from unittest.mock import MagicMock

# Create a class that inherits from Exception to act as a mock exception
class MockDiscordForbidden(Exception): pass
class MockDiscordHTTPException(Exception): pass

class MockDiscordMod:
    Forbidden = MockDiscordForbidden
    HTTPException = MockDiscordHTTPException
    SelectOption = MagicMock

    class User:
        mention = "@mockuser"
    class Member: pass
    class TextChannel: pass
    class Message: pass
    class Interaction: pass

    class abc:
        class Messageable:
            pass

    class Embed:
        def __init__(self, *args, **kwargs):
            pass

    class File:
        def __init__(self, *args, **kwargs):
            pass

    class PermissionOverwrite:
        def __init__(self, *args, **kwargs):
            pass

    class Intents:
        @staticmethod
        def default():
            return MagicMock()

class MockButtonStyle:
    primary = 1
    secondary = 2
    success = 3
    danger = 4
    link = 5

MockDiscordMod.ButtonStyle = MockButtonStyle

mock_discord = MockDiscordMod()
sys.modules['discord'] = mock_discord

class MockUI:
    View = MagicMock
    Button = MagicMock
    Select = MagicMock

    @staticmethod
    def button(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

sys.modules['discord.ui'] = MockUI
mock_discord.ui = MockUI

sys.modules['discord.ext'] = MagicMock()
sys.modules['discord.ext.commands'] = MagicMock()

# Mock discord decorators
def mock_decorator(*args, **kwargs):
    return lambda f: f

class MockAppCommands:
    command = mock_decorator
sys.modules['discord.app_commands'] = MockAppCommands()

# Mock dotenv
sys.modules['dotenv'] = MagicMock()

# Mock aiohttp
sys.modules['aiohttp'] = MagicMock()

# Mock PIL
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageDraw'] = MagicMock()
sys.modules['PIL.ImageFont'] = MagicMock()
