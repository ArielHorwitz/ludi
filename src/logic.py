import random
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum


BOARD_SIZE = 12
BOARD_END = BOARD_SIZE - 1
TRACK_SIZE = BOARD_SIZE * 4
PLAYER_COUNT = 4
UNIT_COUNT = 4
DICE_COUNT = 1
ROLL_MIN = 1
ROLL_MAX = 6
STARTING_POSITIONS = tuple(BOARD_SIZE * i for i in range(PLAYER_COUNT))


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
    index: int
    units: list[Unit] = field(
        default_factory=lambda: [Unit() for i in range(UNIT_COUNT)]
    )
    dice: list[int] = field(
        default_factory=lambda: [i + ROLL_MIN for i in range(DICE_COUNT - 1)]
    )

    def __hash__(self) -> int:
        return hash((self.index, tuple(self.units), tuple(self.dice)))


@dataclass_json
@dataclass
class GameState:
    turn: int = -1
    players: list[Player] = field(
        default_factory=lambda: [Player(i) for i in range(PLAYER_COUNT)]
    )

    @classmethod
    def new_game(cls) -> "GameState":
        game = cls()
        game._iterate_turn()
        return game

    def __hash__(self) -> int:
        return hash((self.turn, tuple(self.players)))

    def get_player(self) -> Player:
        return self.players[self.turn % PLAYER_COUNT]

    def roll_dice(self) -> str:
        # Add dice until we have correct dice count
        player = self.get_player()
        if len(player.dice) == DICE_COUNT:
            return "Dice full"
        while len(player.dice) < DICE_COUNT:
            roll = random.randint(ROLL_MIN, ROLL_MAX)
            player.dice.append(roll)
        return "Rolled"

    def move_unit(self, unit_index: int, die_index: int) -> str:
        player = self.get_player()
        if len(player.dice) < DICE_COUNT:
            return "Must roll first"
        if unit_index < 0 or unit_index >= UNIT_COUNT:
            return f"No such unit {unit_index}"
        if die_index < 0 or die_index >= DICE_COUNT:
            return f"No such die {die_index}"
        # Resolve input
        unit = player.units[unit_index]
        die_value = player.dice[die_index]
        # Resolve result based on unit track and die
        if unit.track == Track.END:
            return "Units that finished cannot move"
        elif unit.track == Track.START:
            # Unit can only leave spawn when rolling the minimum
            if die_value != ROLL_MIN:
                return f"Units in spawn can only move with a {ROLL_MIN}"
            unit.track = Track.MAIN
            unit.position = STARTING_POSITIONS[player.index]
            player.dice.pop(die_index)
            return f"Moved on to track (#{die_index})"
        else:
            # Units on track can always use any die
            assert unit.track == Track.MAIN
            unit.position += die_value
            player.dice.pop(die_index)
            # TODO implement unit capture
            self._iterate_turn()
            return f"Moved +{die_value} (#{die_index})"

    def _iterate_turn(self):
        self.turn += 1
        # Move one unit to track if no units are on track
        player = self.get_player()
        if all(unit.track != Track.MAIN for unit in player.units):
            for unit in player.units:
                if unit.track == Track.START:
                    unit.track = Track.MAIN
                    unit.position = STARTING_POSITIONS[player.index]
                    break
