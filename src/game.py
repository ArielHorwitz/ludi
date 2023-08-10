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


class Area(Enum):
    SPAWN = 1
    TRACK = 2
    FINISH = 3


@dataclass_json
@dataclass
class Unit:
    index: int
    player_index: int
    area: Area = Area.SPAWN
    track_distance: int = 0

    def __hash__(self) -> int:
        return hash((self.player_index, self.index, self.area, self.track_distance))

    @property
    def name(self) -> str:
        return UNIT_NAMES[self.index]

    def get_position(self, *, add_distance: int = 0) -> Optional[int]:
        if not self.on_track:
            return None
        start = STARTING_POSITIONS[self.player_index]
        return (start + self.track_distance + add_distance) % TRACK_SIZE

    @property
    def position(self) -> Optional[int]:
        return self.get_position()

    @property
    def in_spawn(self) -> bool:
        return self.area == Area.SPAWN

    @property
    def on_track(self) -> bool:
        return self.area == Area.TRACK

    @property
    def finished(self) -> bool:
        return self.area == Area.FINISH

    def move_to_spawn(self):
        self.area = Area.SPAWN
        self.track_distance = 0

    def move_to_track(self, starting_handicap: bool = False):
        self.area = Area.TRACK
        if starting_handicap:
            self.track_distance = TURN_ORDER_HANDICAP[self.player_index]
        else:
            self.track_distance = 0

    def move_to_finish(self):
        self.area = Area.FINISH
        self.track_distance = TRACK_SIZE

    def can_use_die(self, die_value: int) -> bool:
        if self.finished:
            return False
        if self.in_spawn:
            return die_value in RESCUE_ROLLS
        return True

    @property
    def is_safe(self) -> bool:
        assert None not in SAFE_POSITIONS
        return self.position in SAFE_POSITIONS


@dataclass_json
@dataclass
class Player:
    index: int
    units: list[Unit] = field(default_factory=list)
    dice: list[int] = field(
        default_factory=lambda: [i + ROLL_MIN for i in range(DICE_COUNT - 1)]
    )

    def __post_init__(self):
        if len(self.units) == 0:
            self.units.extend([Unit(i, self.index) for i in range(UNIT_COUNT)])
        else:
            assert len(self.units) == UNIT_COUNT

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
        return tuple(u.index for u in self.units if not u.finished)


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
            unit.move_to_track(starting_handicap=True)
        return game

    def __hash__(self) -> int:
        return hash((self.turn, tuple(self.players), tuple(self.log)))

    def get_player(self) -> Player:
        return self.players[self.turn % PLAYER_COUNT]

    def roll_dice(self) -> bool:
        player = self.get_player()
        # Rescue to have at least one unit on the track
        if not any(unit.on_track for unit in player.units):
            for unit in player.units:
                if unit.in_spawn:
                    # Rescue
                    unit.move_to_track()
                    break
        # Add dice until we have correct dice count
        if len(player.dice) == DICE_COUNT:
            return False
        while len(player.dice) < DICE_COUNT:
            die_value = random.randint(ROLL_MIN, ROLL_MAX)
            player.dice.append(die_value)
            self.log[-1] += tokenizer.roll_die(die_value)
        player.dice.sort()
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
        if unit.finished:
            return False
        elif unit.in_spawn:
            if die_value not in RESCUE_ROLLS:
                return False
            player.dice.pop(die_index)
            unit.move_to_track()
            self.log[-1] += tokenizer.unit_spawn(unit.name, die_value)
            return True
        else:
            assert unit.on_track
            player.dice.pop(die_index)
            unit.track_distance += die_value
            turn_ends = True
            if unit.track_distance >= TRACK_SIZE:
                unit.move_to_finish()
                self.log[-1] += tokenizer.unit_finish(unit.name, die_value)
                if all(unit.finished for unit in player.units):
                    self.winner = player.index
                    self.log[-1] += tokenizer.Symbol.GAME_OVER
                    turn_ends = False
            else:
                captured = self._do_capture(unit)
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

    def _do_capture(self, unit: Unit) -> list[tuple[str, str]]:
        assert unit.on_track
        capture_position = unit.position
        if capture_position in SAFE_POSITIONS:
            return []
        captured = []
        for enemy_player in self.players:
            if enemy_player.index == unit.player_index:
                continue
            for enemy_unit in enemy_player.units:
                if capture_position == enemy_unit.position:
                    enemy_unit.move_to_spawn()
                    captured.append((enemy_player.name, enemy_unit.name))
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
        units = player.units
        turns_away = (player.index - self.get_player().index) % PLAYER_COUNT
        turn_normalized = (PLAYER_COUNT - turns_away - 1) / PLAYER_COUNT
        finished_units = [u for u in units if u.finished]
        finish_normalized = len(finished_units) / UNIT_COUNT
        spawning_units = [u for u in units if u.in_spawn]
        spawn_normalized = len(spawning_units) / UNIT_COUNT
        safe_units = [u for u in units if u.on_track and u.is_safe]
        safe_normalized = len(safe_units) / UNIT_COUNT
        all_progress = [p.get_progress() for p in self.players]
        player_progress_normalized = all_progress.pop(player_index)
        enemy_progress_normalized = sum(all_progress) / len(all_progress)
        if DICE_COUNT > 1:
            dice_value = sum(player.dice) / (DICE_COUNT - 1)
            dice_normalized = (dice_value - ROLL_MIN) / (ROLL_MAX - ROLL_MIN)
        else:
            dice_normalized = 0
        total = sum(
            [
                turn_normalized * BotEvalWeights.turn,
                finish_normalized * BotEvalWeights.finish,
                safe_normalized * BotEvalWeights.safe,
                spawn_normalized * BotEvalWeights.spawn,
                player_progress_normalized * BotEvalWeights.progress,
                enemy_progress_normalized * BotEvalWeights.enemy_progress,
                dice_normalized * BotEvalWeights.dice,
            ]
        )
        logger.debug(
            "\n".join(
                [
                    f"Bot Evaluation for: {player.name} (turn {self.turn})",
                    "\n".join(self.log[-2:]),
                    f"                {turns_away=}",
                    f"            {finished_units=}",
                    f"                {safe_units=}",
                    f"            {spawning_units=}",
                    f"{player_progress_normalized=}",
                    f" {enemy_progress_normalized=}",
                    f"           {dice_normalized=}",
                    f"                     {total=}",
                ]
            )
        )
        return total
