import copy
import itertools
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple, Optional

from dataclasses_json import dataclass_json
from loguru import logger

import tokenizer
from config import (
    BOARD_SIZE,
    DICE_COUNT,
    RESCUE_ROLLS,
    ROLL_MAX,
    ROLL_MIN,
    SAFE_POSITION_OFFSET,
    UNIT_COUNT,
)

PLAYER_COUNT = 4
TRACK_SIZE = BOARD_SIZE * 4
_AVG_ROLL = (ROLL_MIN + ROLL_MAX) / 2
ALL_POSSIBLE_MOVES = tuple(
    itertools.product(
        list(range(UNIT_COUNT)),
        list(range(DICE_COUNT)),
    )
)
STARTING_POSITIONS = tuple(BOARD_SIZE * i for i in range(PLAYER_COUNT))
STAR_POSITIONS = tuple(
    BOARD_SIZE * i + SAFE_POSITION_OFFSET for i in range(PLAYER_COUNT)
)
SAFE_POSITIONS = frozenset(set(STARTING_POSITIONS) | set(STAR_POSITIONS))
TURN_ORDER_HANDICAP = tuple(
    round(_AVG_ROLL * i / PLAYER_COUNT) for i in range(PLAYER_COUNT)
)
UNIT_NAMES = "ABCDEFGHIJ"


class BotEvalWeights:
    turn = 10
    finish = 20
    safe = 5
    spawn = -5
    progress = 20
    enemy_progress = -20
    dice = 0.5


class BotMove(NamedTuple):
    unit: int
    die: int
    state: "GameState"


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

    def can_use_die(self, die_value: int) -> bool:
        if self.position == Position.FINISH:
            return False
        if self.position == Position.SPAWN:
            return die_value in RESCUE_ROLLS
        return True


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

    @property
    def missing_dice(self) -> bool:
        return len(self.dice) < DICE_COUNT

    @property
    def movable_units(self) -> tuple[int, ...]:
        return tuple(u.index for u in self.units if u.position != Position.FINISH)


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
        game.log.append(tokenizer.turn_start(game.get_player().name))
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
            turn_ends = True
            if unit.track_distance >= TRACK_SIZE:
                unit.track_distance = TRACK_SIZE
                unit.position = Position.FINISH
                self.log[-1] += tokenizer.unit_finish(unit.name, die_value)
                if all(unit.position == Position.FINISH for unit in player.units):
                    self.winner = player.index
                    self.log[-1] += tokenizer.Symbol.GAME_OVER
                    turn_ends = False
            else:
                captured = self._do_capture(
                    player.index,
                    unit.get_position(player.index),
                )
                if captured:
                    turn_ends = False
                    self.log[-1] += tokenizer.unit_capture(
                        unit.name, die_value, captured
                    )
                else:
                    turn_ends = die_value != ROLL_MAX
                    self.log[-1] += tokenizer.unit_move(unit.name, die_value)
            if turn_ends:
                self.turn += 1
                self.log.append(tokenizer.turn_start(self.get_player().name))
            return True

    def _do_capture(
        self,
        player_index: int,
        capture_position: int,
    ) -> list[tuple[str, str]]:
        if capture_position in SAFE_POSITIONS:
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

    def play_bot(self):
        if self.roll_dice():
            return
        possible_moves = list(ALL_POSSIBLE_MOVES)
        random.shuffle(possible_moves)
        state = copy.deepcopy(self)
        legal_moves = []
        for unit_index, die_index in possible_moves:
            if state.move_unit(unit_index, die_index):
                legal_moves.append(BotMove(unit_index, die_index, state))
                state = copy.deepcopy(self)
        if len(legal_moves) == 0:
            raise RuntimeError("No legal move found!")
        player_index = self.get_player().index
        best_move = sorted(
            legal_moves,
            key=lambda m: m.state.bot_evaluation(player_index),
        )[-1]
        self.move_unit(best_move.unit, best_move.die)

    def bot_evaluation(self, player_index: int) -> float:
        player = self.players[player_index]
        turns_away = (player.index - self.get_player().index) % PLAYER_COUNT
        turn = (PLAYER_COUNT - turns_away - 1) / PLAYER_COUNT
        units = player.units
        finished_units = [u for u in units if u.position == Position.FINISH]
        finish = len(finished_units) / UNIT_COUNT
        spawning_units = [u for u in units if u.position == Position.SPAWN]
        spawn = len(spawning_units) / UNIT_COUNT
        safe_units = [
            u
            for u in units
            if (
                u.position == Position.TRACK
                and u.get_position(player_index) in SAFE_POSITIONS
            )
        ]
        safe = len(safe_units) / UNIT_COUNT
        progress = player.get_progress()
        total_enemy_progress = sum(p.get_progress() for p in self.players) - progress
        enemy_progress = total_enemy_progress / (PLAYER_COUNT - 1)
        if DICE_COUNT > 1:
            dice_value = sum(player.dice) / (DICE_COUNT - 1)
            dice = (dice_value - ROLL_MIN) / (ROLL_MAX - ROLL_MIN)
        else:
            dice = 0
        total = sum(
            [
                turn * BotEvalWeights.turn,
                finish * BotEvalWeights.finish,
                safe * BotEvalWeights.safe,
                spawn * BotEvalWeights.spawn,
                progress * BotEvalWeights.progress,
                enemy_progress * BotEvalWeights.enemy_progress,
                dice * BotEvalWeights.dice,
            ]
        )
        logger.debug(
            "\n".join(
                [
                    f"Bot Evaluation for: {player.name} (turn {self.turn})",
                    "\n".join(self.log[-2:]),
                    f"          {turn=}",
                    f"{finished_units=}",
                    f"    {safe_units=}",
                    f"{spawning_units=}",
                    f"      {progress=}",
                    f"{enemy_progress=}",
                    f"          {dice=}",
                    f"         {total=}",
                ]
            )
        )
        return total
