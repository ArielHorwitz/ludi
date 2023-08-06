from enum import Enum


class EventType(Enum):
    TURN_START = 1
    DICE_ROLLED = 2
    UNIT_SPAWN = 3
    UNIT_FINISH = 4
    UNIT_MOVE = 5
    UNIT_CAPTURE = 6


def start_turn(player_name: str) -> str:
    return f" {player_name}:"


def roll_die(die_value: int) -> str:
    return f" {die_value}/"


def unit_spawn(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}+"


def unit_finish(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}!"


def unit_move(unit_name: str, die_value: int) -> str:
    return f" {unit_name}{die_value}."


def unit_capture(
    unit_name: str,
    die_value: int,
    captured: list[tuple[str, str]],
) -> str:
    assert len(captured) > 0
    token = f"{unit_name}{die_value}"
    for p, u in captured:
        token += f"x{p}{u}"
    return token


def tokenize_word(word: str) -> EventType:
    word, original = word.strip(), word
    if word.endswith(":"):
        return EventType.TURN_START
    if word.endswith("/"):
        return EventType.DICE_ROLLED
    if word.endswith("."):
        return EventType.UNIT_MOVE
    if "x" in word:
        return EventType.UNIT_CAPTURE
    if word.endswith("+"):
        return EventType.UNIT_SPAWN
    if "!" in word:
        return EventType.UNIT_FINISH
    raise RuntimeError(f"Tokenization failed: {original!r}")


def tokenize_turn(log_turn: str) -> list[EventType]:
    return [tokenize_word(word.strip()) for word in log_turn.split() if word.strip()]
