import random
from pathlib import Path

import kvex as kx
from loguru import logger

from tokenizer import EventType

# Game Rules
BOARD_SIZE = 13
UNIT_COUNT = 4
DICE_COUNT = 2
ROLL_MIN = 1
ROLL_MAX = 6
SAFE_POSITION_OFFSET = 8
RESCUE_ROLLS = frozenset([ROLL_MIN, ROLL_MAX])

# GUI
DEFAULT_VOLUME = 0.5
ANIMATION_FPS = 15
PLAYER_COLORS = (
    kx.XColor.from_name("blue"),
    kx.XColor.from_name("green"),
    kx.XColor.from_name("yellow"),
    kx.XColor.from_name("red"),
)
TURN_START_SFX_DELAY = 0.2
GUI_REFRESH_TIMEOUT = 0.5


# Assets
ASSET_DIR = Path(__file__).parent / "assets"
SFX_DIR = ASSET_DIR / "sfx"
DICE_IMAGES_DIR = ASSET_DIR / "images" / "dice"
DICE_SFX_DIR = SFX_DIR / "dice"
logger.info(f"{DICE_SFX_DIR=}")
for f in (DICE_SFX_DIR).iterdir():
    logger.info(f)
DICE_SFX = tuple(kx.SoundLoader.load(str(f)) for f in (DICE_SFX_DIR).iterdir())
EVENT_SFX_DIR = SFX_DIR / "events"
EVENT_SFX_FILES = {
    evtype: EVENT_SFX_DIR / f"{evtype.name.lower().replace('_', '-')}.wav"
    for evtype in EventType
    if evtype != EventType.DICE_ROLLED
}
EVENT_SFX = {
    evtype: kx.SoundLoader.load(str(path)) for evtype, path in EVENT_SFX_FILES.items()
}
VICTORY_SFX = kx.SoundLoader.load(str(SFX_DIR / "victory.wav"))
UI_CLICK1 = kx.SoundLoader.load(str(SFX_DIR / "ui-click1.wav"))
UI_CLICK2 = kx.SoundLoader.load(str(SFX_DIR / "ui-click2.wav"))


def play_sfx(sfx):
    logger.debug(f"{Path(sfx.source).is_file()}, {sfx.source}")
    if sfx.get_pos():
        sfx.stop()
    sfx.volume = DEFAULT_VOLUME
    sfx.play()


def play_event_sfx(event: EventType):
    if event == EventType.DICE_ROLLED:
        return play_sfx(random.choice(DICE_SFX))
    play_sfx(EVENT_SFX[event])
