import pytest
from src.game_models import GameState, Player, Faction, Werewolf, Seer, Villager, GamePhase
from unittest.mock import MagicMock

class MockUser:
    def __init__(self, name="TestUser"):
        self.display_name = name

class MockChannel:
    pass

def test_player_creation():
    mock_user = MockUser()
    player = Player(mock_user, 1)

    assert player.number == 1
    assert player.is_alive == True
    assert player.role is None
    assert str(player) == "[1號] TestUser"

def test_game_over_wolves_win():
    mock_channel = MockChannel()
    mock_creator = MockUser()
    game = GameState(mock_channel, mock_creator)
    game.phase = GamePhase.DAY

    # Setup 1 Wolf, 1 Villager, 0 Gods (Gods are dead)
    p1 = Player(MockUser(), 1)
    p1.role = Werewolf()
    game.add_player(p1)

    p2 = Player(MockUser(), 2)
    p2.role = Villager()
    game.add_player(p2)

    game.wolf_count = 1
    game.villager_count = 1
    game.god_count = 1 # There was a god, but they are removed/dead

    winner = game.check_game_over()
    assert winner == Faction.WOLF

def test_game_over_good_wins():
    mock_channel = MockChannel()
    mock_creator = MockUser()
    game = GameState(mock_channel, mock_creator)
    game.phase = GamePhase.DAY

    # Setup 0 Wolves, 1 Villager, 1 God
    p1 = Player(MockUser(), 1)
    p1.role = Villager()
    game.add_player(p1)

    p2 = Player(MockUser(), 2)
    p2.role = Seer()
    game.add_player(p2)

    game.wolf_count = 1 # Started with 1 wolf
    game.villager_count = 1
    game.god_count = 1

    winner = game.check_game_over()
    assert winner == Faction.VILLAGER
