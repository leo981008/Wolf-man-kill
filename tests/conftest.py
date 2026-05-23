import sys
from unittest.mock import MagicMock

# Conditionally mock dependencies only if they are not installed in the environment
try:
    import discord
except ImportError:
    mock_discord = MagicMock()
    sys.modules['discord'] = mock_discord
    sys.modules['discord.ext'] = MagicMock()
    sys.modules['discord.ext.commands'] = MagicMock()
    sys.modules['discord.app_commands'] = MagicMock()

try:
    import dotenv
except ImportError:
    sys.modules['dotenv'] = MagicMock()

try:
    import aiohttp
except ImportError:
    sys.modules['aiohttp'] = MagicMock()

try:
    import PIL
except ImportError:
    sys.modules['PIL'] = MagicMock()

# Always mock google modules as they are not used directly but tests expect them mock-defined
sys.modules['google'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()

import pytest
from unittest.mock import AsyncMock

@pytest.fixture(autouse=True)
def mock_ai_manager_calls(monkeypatch):
    """
    Globally mock AIManager's narrative generation methods during testing to prevent actual API requests.
    We do NOT mock generate_response globally, because some tests need to verify its retry/request logic.
    """
    try:
        from ai_manager import ai_manager
        # Mock only on the singleton instance to let new AIManager instances run real narrative code in tests
        monkeypatch.setattr(ai_manager, "generate_narrative", AsyncMock(return_value="[Atmosphere Narrative]"))
    except ImportError:
        pass


