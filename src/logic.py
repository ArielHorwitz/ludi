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
_AVG_ROLL = (ROLL_MIN + ROLL_MAX) / 2
STARTING_POSITIONS = tuple(BOARD_SIZE * i for i in range(PLAYER_COUNT))
TURN_ORDER_HANDICAP = tuple(
    round(_AVG_ROLL * i / PLAYER_COUNT) for i in range(PLAYER_COUNT)
)


class Position(Enum):
    SPAWN = 1
    TRACK = 2
    FINISH = 3


@dataclass_json
@dataclass
class Unit:
    index: int
    position: Position = Position.SPAWN
    track_position: int = 0

    def __hash__(self) -> int:
        return hash((self.index, self.position, self.track_position))


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


@dataclass_json
@dataclass
class GameState:
    turn: int = 0
    players: list[Player] = field(
        default_factory=lambda: [Player(i) for i in range(PLAYER_COUNT)]
    )

    @classmethod
    def new_game(cls) -> "GameState":
        game = cls()
        # Start all units
        for player in game.players:
            unit = player.units[0]
            unit.position = Position.TRACK
            handicap = TURN_ORDER_HANDICAP[player.index]
            unit.track_position = STARTING_POSITIONS[player.index] + handicap
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
        if unit.position == Position.FINISH:
            return "Units that finished cannot move"
        elif unit.position == Position.SPAWN:
            if die_value != ROLL_MIN:
                return f"Units in spawn can only move with a {ROLL_MIN}"
            player.dice.pop(die_index)
            unit.position = Position.TRACK
            unit.track_position = STARTING_POSITIONS[player.index]
            return f"Moved on #{unit.index + 1} to track"
        else:
            # Units on track can always use any die
            assert unit.position == Position.TRACK
            player.dice.pop(die_index)
            unit.track_position += die_value
            response = f"Moved +{die_value}"
            captured = self._capture(player.index, unit.track_position)
            if captured:
                captured_repr = " ".join([f"({p + 1},{u + 1})" for p, u in captured])
                response = f"{response}, captured {captured_repr}"
            turn_over = die_value != ROLL_MAX and not captured
            if turn_over:
                self.turn += 1
            return response

    def _capture(
        self,
        player_index: int,
        capture_position: int,
    ) -> list[tuple[int, int]]:
        capture_position %= TRACK_SIZE
        if capture_position in STARTING_POSITIONS:
            return []
        captured = []
        for player in self.players:
            if player.index == player_index:
                # Ignore friendly units
                continue
            for unit in player.units:
                if capture_position == unit.track_position % TRACK_SIZE:
                    # Capture
                    unit.position = Position.SPAWN
                    unit.track_position = STARTING_POSITIONS[player.index]
                    captured.append((player.index, unit.index))
            # Leave at least one unit per player on the track
            if all(unit.position != Position.TRACK for unit in player.units):
                for unit in player.units:
                    if unit.position == Position.SPAWN:
                        # Rescue
                        unit.position = Position.TRACK
                        unit.track_position = STARTING_POSITIONS[player.index]
                        break
        return captured
