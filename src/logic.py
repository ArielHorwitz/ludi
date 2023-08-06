from typing import Optional
import random
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from enum import Enum
import tokenizer


BOARD_SIZE = 12
UNIT_COUNT = 4
DICE_COUNT = 2
ROLL_MIN = 1
ROLL_MAX = 6
TRACK_SIZE = BOARD_SIZE * 4
PLAYER_COUNT = 4
RESCUE_ROLLS = frozenset([ROLL_MIN, ROLL_MAX])
_AVG_ROLL = (ROLL_MIN + ROLL_MAX) / 2
STARTING_POSITIONS = tuple(BOARD_SIZE * i for i in range(PLAYER_COUNT))
TURN_ORDER_HANDICAP = tuple(
    round(_AVG_ROLL * i / PLAYER_COUNT) for i in range(PLAYER_COUNT)
)
UNIT_NAMES = "ABCDEFGHIJ"


class Position(Enum):
    SPAWN = 1
    TRACK = 2
    FINISH = 3


@dataclass_json
@dataclass
class Unit:
    index: int
    position: Position = Position.SPAWN
    track_distance: int = 0

    def __hash__(self) -> int:
        return hash((self.index, self.position, self.track_distance))

    def get_position(self, player_index: int):
        track_position = self.track_distance + STARTING_POSITIONS[player_index]
        return track_position % TRACK_SIZE

    @property
    def name(self) -> str:
        return UNIT_NAMES[self.index]


@dataclass_json
@dataclass
class Player:
    index: int
    units: list[Unit] = field(
        default_factory=lambda: [Unit(i) for i in range(UNIT_COUNT)]
    )
    dice: list[int] = field(
        default_factory=lambda: [i + ROLL_MIN for i in range(DICE_COUNT - 1)]
    )

    def __hash__(self) -> int:
        return hash((self.index, tuple(self.units), tuple(self.dice)))

    def get_progress(self) -> float:
        return sum(u.track_distance for u in self.units) / TRACK_SIZE / UNIT_COUNT

    @property
    def name(self) -> str:
        return str(self.index + 1)


@dataclass_json
@dataclass
class GameState:
    turn: int = 0
    players: list[Player] = field(
        default_factory=lambda: [Player(i) for i in range(PLAYER_COUNT)]
    )
    log: list[str] = field(default_factory=lambda: [])
    winner: Optional[int] = None

    @classmethod
    def new_game(cls) -> "GameState":
        game = cls()
        game.log.append(tokenizer.start_turn(game.get_player().name))
        # Start all units
        for player in game.players:
            unit = player.units[0]
            unit.position = Position.TRACK
            unit.track_distance = TURN_ORDER_HANDICAP[player.index]
        return game

    def __hash__(self) -> int:
        return hash((self.turn, tuple(self.players), tuple(self.log)))

    def get_player(self) -> Player:
        return self.players[self.turn % PLAYER_COUNT]

    def roll_dice(self) -> bool:
        player = self.get_player()
        # Rescue to have at least one unit on the track
        if all(unit.position != Position.TRACK for unit in player.units):
            for unit in player.units:
                if unit.position == Position.SPAWN:
                    # Rescue
                    unit.position = Position.TRACK
                    unit.track_distance = 0
                    break
        # Add dice until we have correct dice count
        if len(player.dice) == DICE_COUNT:
            return False
        while len(player.dice) < DICE_COUNT:
            die_value = random.randint(ROLL_MIN, ROLL_MAX)
            player.dice.append(die_value)
            self.log[-1] += tokenizer.roll_die(die_value)
        return True

    def move_unit(self, unit_index: int, die_index: int) -> bool:
        player = self.get_player()
        if len(player.dice) < DICE_COUNT:
            return False
        if unit_index < 0 or unit_index >= UNIT_COUNT:
            return False
        if die_index < 0 or die_index >= DICE_COUNT:
            return False
        unit = player.units[unit_index]
        die_value = player.dice[die_index]
        if unit.position == Position.FINISH:
            return False
        elif unit.position == Position.SPAWN:
            if die_value not in RESCUE_ROLLS:
                return False
            player.dice.pop(die_index)
            unit.position = Position.TRACK
            unit.track_distance = 0
            self.log[-1] += tokenizer.unit_spawn(unit.name, die_value)
            return True
        else:
            assert unit.position == Position.TRACK
            player.dice.pop(die_index)
            unit.track_distance += die_value
            extra_turn = False
            if unit.track_distance >= TRACK_SIZE:
                unit.track_distance = TRACK_SIZE
                unit.position = Position.FINISH
                self.log[-1] += tokenizer.unit_finish(unit.name, die_value)
                if all(unit.position == Position.FINISH for unit in player.units):
                    self.winner = player.index
            else:
                captured = self._do_capture(
                    player.index,
                    unit.get_position(player.index),
                )
                if captured:
                    extra_turn = True
                    self.log[-1] += tokenizer.unit_capture(
                        unit.name, die_value, captured
                    )
                else:
                    extra_turn = die_value == ROLL_MAX
                    self.log[-1] += tokenizer.unit_move(unit.name, die_value)
            if not extra_turn:
                self.turn += 1
                self.log.append(tokenizer.start_turn(self.get_player().name))
            return True

    def _do_capture(
        self,
        player_index: int,
        capture_position: int,
    ) -> list[tuple[str, str]]:
        if capture_position in STARTING_POSITIONS:
            return []
        captured = []
        for player in self.players:
            if player.index == player_index:
                # Ignore friendly units
                continue
            for unit in player.units:
                if capture_position == unit.get_position(player.index):
                    # Capture
                    unit.position = Position.SPAWN
                    unit.track_distance = 0
                    captured.append((player.name, unit.name))
        return captured
