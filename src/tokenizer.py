from enum import Enum


class Symbol:
    START = ":"
    DICE = "/"
    SPAWN = "+"
    MOVE = "."
    CAPTURE = "x"
    FINISH = "!"
    GAME_OVER = "#"


class EventType(Enum):
    TURN_START = 1
    DICE_ROLLED = 2
    UNIT_SPAWN = 3
    UNIT_FINISH = 4
    UNIT_MOVE = 5
    UNIT_CAPTURE = 6


def turn_start(player_name: str) -> str:
    return f" {player_name}{Symbol.START}"


def roll_die(die_value: int) -> str:
    return f" {die_value}{Symbol.DICE}"


def unit_spawn(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}{Symbol.SPAWN}"


def unit_finish(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}{Symbol.FINISH}"


def unit_move(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}{Symbol.MOVE}"


def unit_capture(
    unit_name: str,
    die_value: int,
    captured: list[tuple[str, str]],
) -> str:
    assert len(captured) > 0
    token = f"{unit_name}{die_value}"
    for p, u in captured:
        token += f"{Symbol.CAPTURE}{p}{u}"
    return token


def tokenize_word(word: str) -> EventType:
    word, original = word.strip(), word
    if word.endswith(Symbol.GAME_OVER):
        word = word[:-1]
    if word.endswith(Symbol.START):
        return EventType.TURN_START
    if word.endswith(Symbol.DICE):
        return EventType.DICE_ROLLED
    if word.endswith(Symbol.MOVE):
        return EventType.UNIT_MOVE
    if Symbol.CAPTURE in word:
        return EventType.UNIT_CAPTURE
    if word.endswith(Symbol.SPAWN):
        return EventType.UNIT_SPAWN
    if word.endswith(Symbol.FINISH):
        return EventType.UNIT_FINISH
    raise RuntimeError(f"Tokenization failed: {original!r}")


def tokenize_turn(log_turn: str) -> list[EventType]:
    return [
        tokenize_word(word.strip()) for word in log_turn.strip().split() if word.strip()
    ]
