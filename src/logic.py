import random
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum


BOARD_SIZE = 12
BOARD_END = BOARD_SIZE - 1
TRACK_SIZE = BOARD_SIZE * 4
PLAYER_COUNT = 4
UNIT_COUNT = 4
STARTING_POSITIONS = tuple(BOARD_SIZE * i for i in range(UNIT_COUNT))


class Track(Enum):
    START = 1
    MAIN = 2
    END = 3


@dataclass_json
@dataclass
class Unit:
    position: int = 0
    track: Track = Track.START

    def __hash__(self) -> int:
        return hash((self.position, self.track))


@dataclass_json
@dataclass
class Player:
    name: str
    units: list[Unit] = field(
        default_factory=lambda: [Unit() for i in range(UNIT_COUNT)]
    )

    def __hash__(self) -> int:
        return hash((self.name, tuple(self.units)))


@dataclass_json
@dataclass
class GameState:
    seed: float = field(default_factory=random.random)
    players: list[Player] = field(
        default_factory=lambda: [Player(str(i)) for i in range(PLAYER_COUNT)]
    )
    turn: int = 0

    def __hash__(self) -> int:
        return hash((self.seed, tuple(self.players), self.turn))


def get_dice_roll():
    return random.randint(BOARD_SIZE // 8, BOARD_SIZE // 2 - 1)
