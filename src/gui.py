from typing import Optional
from pathlib import Path
import random
import kvex as kx
import pgnet
import logic
import tokenizer
from loguru import logger
from tokenizer import EventType
from functools import partial


PLAYER_COLORS = (
    kx.XColor.from_name("blue"),
    kx.XColor.from_name("green"),
    kx.XColor.from_name("yellow"),
    kx.XColor.from_name("red"),
)
PLAYER_ANCHORS = [
    ("left", "bottom"),
    ("left", "top"),
    ("right", "top"),
    ("right", "bottom"),
]
ASSET_DIR = Path(__file__).parent / "assets"
DICE_SFX = tuple(kx.SoundLoader.load(str(f)) for f in (ASSET_DIR / "dice").iterdir())
EVENT_SFX_FILES = {
    evtype: ASSET_DIR / "sfx" / f"{evtype.name.lower().replace('_', '-')}.wav"
    for evtype in EventType
}
EVENT_SFX = {
    evtype: kx.SoundLoader.load(str(path)) for evtype, path in EVENT_SFX_FILES.items()
}
TURN_START_SFX_DELAY = 0.2
GUI_REFRESH_TIMEOUT = 0.5


def play_event_sfx(event: EventType):
    if event == EventType.DICE_ROLLED:
        sfx = random.choice(DICE_SFX)
    else:
        sfx = EVENT_SFX[event]
    if sfx.get_pos():
        sfx.stop()
    sfx.play()


class GameWidget(kx.XFrame):
    def __init__(self, client: pgnet.Client, **kwargs):
        super().__init__(**kwargs)
        self.state_hash = None
        self.state = logic.GameState.new_game()
        self.player_names = set()
        self.chosen_die: Optional[int] = None
        self.__refresh_trigger = kx.create_trigger(
            self._full_refresh,
            timeout=GUI_REFRESH_TIMEOUT,
        )
        self.client = client
        self._make_widgets()
        hotkeys = self.app.game_controller
        hotkeys.register("force refresh", "^ f5", self._full_refresh)
        hotkeys.register("slow down bots", "-", partial(self._user_set_bot_play_interval, 0.5))
        hotkeys.register("speed up bots", "=", partial(self._user_set_bot_play_interval, -0.5))
        hotkeys.register("leave", "^ escape", self.client.leave_game)
        hotkeys.register("roll", "spacebar", self._user_roll)
        hotkeys.register("roll", "`")
        hotkeys.register("roll", "escape")
        for i in range(max(logic.UNIT_COUNT, logic.DICE_COUNT)):
            control = keynumber = str(i + 1)
            hotkeys.register(control, keynumber)  # Number keys
            hotkeys.register(control, f"f{keynumber}")  # F keys
            hotkeys.bind(control, partial(self._select_index, i))
        client.on_heartbeat = self.on_heartbeat
        client.heartbeat_payload = self.heartbeat_payload
        self.bind(size=self._trigger_refresh)
        self._trigger_refresh()

    def on_subtheme(self, *args, **kwargs):
        super().on_subtheme(*args, **kwargs)
        self._refresh_widgets()

    def on_heartbeat(self, heartbeat_response: pgnet.Response):
        state = heartbeat_response.payload.get("state")
        if state is None:
            return
        self.state = logic.GameState.from_json(state)
        logger.debug(f"New game state ({hash(self.state)})")
        last_event = tokenizer.tokenize_turn(self.state.log[-1])[-1]
        if last_event == EventType.TURN_START and len(self.state.log) > 1:
            prev_event = tokenizer.tokenize_turn(self.state.log[-2])[-1]
            play_event_sfx(prev_event)
        else:
            play_event_sfx(last_event)
        self._refresh_widgets()

    def heartbeat_payload(self) -> str:
        return dict(state_hash=hash(self.state))

    def _on_response(self, response: pgnet.Response):
        logger.debug(response)
        self.chosen_die = None
        self._refresh_widgets()

    def _make_widgets(self):
        self.clear_widgets()
        self.make_bg(kx.XColor(0.3, 0.3, 0.3))
        self.track_squares = []
        self.board_frame = kx.XRelative()
        self.spawn_frame = kx.XRelative()
        self.spawn_frame.set_size(hx=0.3, hy=0.3)
        for i in range(logic.TRACK_SIZE):
            track_square = TrackSquare(i)
            self.board_frame.add_widget(track_square)
            self.track_squares.append(track_square)
        self.unit_sprites = []
        self.dice_boxes = []
        self.dice_frame = kx.XAnchor()
        self.dice_frame.set_size(hx=0.8, hy=0.8)
        for player_index, (ax, ay) in enumerate(PLAYER_ANCHORS):
            dicebox = DiceBox(player_index)
            self.dice_frame.add_widget(kx.wrap(dicebox, anchor_x=ax, anchor_y=ay))
            self.dice_boxes.append(dicebox)
            self.unit_sprites.append([])
            for unit_index in range(logic.UNIT_COUNT):
                unit = UnitSprite(player_index, unit_index)
                self.unit_sprites[-1].append(unit)
        board_frame = kx.XAnchor()
        board_frame.add_widgets(self.board_frame, self.spawn_frame, self.dice_frame)
        self.add_widget(board_frame)

    def _trigger_refresh(self, *args):
        kx.snooze_trigger(self.__refresh_trigger)

    def _full_refresh(self, *args):
        self._refresh_geometry()
        kx.schedule_once(self._refresh_widgets)

    def _refresh_geometry(self, *args):
        width = self.board_frame.width
        height = self.board_frame.height
        square_x = width / (logic.BOARD_SIZE + 1)
        square_y = height / (logic.BOARD_SIZE + 1)
        for i, square in enumerate(self.track_squares):
            square.set_size(square_x * 0.9, square_y * 0.9)
            quarter = i // logic.BOARD_SIZE
            offset = i % logic.BOARD_SIZE
            match quarter:
                case 0:
                    square.x = 0
                    square.y = square_y * offset
                case 1:
                    square.x = square_x * offset
                    square.y = height - square_y
                case 2:
                    square.x = width - square_x
                    square.y = height - square_y * (offset + 1)
                case 3:
                    square.x = width - square_x * (offset + 1)
                    square.y = 0
                case _:
                    square.x = square_x
                    square.y = square_y

    def _refresh_widgets(self, *args):
        player = self.state.get_player()
        current_index = player.index
        for player, sprites in zip(self.state.players, self.unit_sprites):
            highlight = player.index == current_index
            highlight_die = self.chosen_die if highlight else None
            self.dice_boxes[player.index].set_dice(
                player.dice, highlight, highlight_die
            )
            starting_square = self.track_squares[logic.STARTING_POSITIONS[player.index]]
            starting_square.label.text = f"{round(100 * player.get_progress(), 1)}%"
            for unit, sprite in reversed(list(zip(player.units, sprites))):
                match unit.position:
                    case logic.Position.FINISH:
                        sprite.remove_from_parent()
                    case logic.Position.SPAWN:
                        sprite.move_to_spawn(self.spawn_frame)
                    case logic.Position.TRACK:
                        square = self.track_squares[unit.get_position(player.index)]
                        sprite.move_to_track(square)

    def _user_roll(self):
        self.client.send(pgnet.Packet("roll"), self._on_response)
        self._refresh_widgets()

    def _select_index(self, index: int):
        if self.chosen_die is None:
            self.chosen_die = index
        else:
            payload = dict(die_index=self.chosen_die, unit_index=index)
            self.client.send(pgnet.Packet("move", payload), self._on_response)
        self._refresh_widgets()

    def _user_set_bot_play_interval(self, delta):
        payload = dict(delta=delta)
        self.client.send(
            pgnet.Packet("set_bot_play_interval", payload),
            self._on_response,
        )


class TrackSquare(kx.XAnchor):
    def __init__(self, position: int):
        super().__init__()
        self.unit_frame = kx.XRelative()
        offset = position % logic.BOARD_SIZE
        self.label = kx.XLabel(text=str(offset), enable_theming=False)
        color = PLAYER_COLORS[position // logic.BOARD_SIZE]
        if position in logic.STARTING_POSITIONS:
            color = color.modified_value(0.5)
        elif position in logic.STAR_POSITIONS:
            color = color.modified_saturation(0.2)
        else:
            color = color.modified_value(0.2)
        self.add_widget(self.label)
        self.add_widget(self.unit_frame)
        self.make_bg(color)


class UnitSprite(kx.XAnchor):
    def __init__(self, player_index: int, unit_index: int):
        super().__init__()
        self.player_index = player_index
        self.unit_index = unit_index
        self.make_bg(color=PLAYER_COLORS[player_index], source=ASSET_DIR / "unit.png")
        self.label = kx.XLabel(
            text=logic.UNIT_NAMES[unit_index],
            enable_theming=False,
            color=(0, 0, 0),
            outline_color=(1, 1, 1),
            outline_width="2sp",
            bold=True,
            font_size="30sp",
        )
        self.add_widget(self.label)

    def move_to_spawn(self, frame):
        self.remove_from_parent()
        self.set_size(hx=0.25, hy=0.25)
        self.x = self.unit_index * self.width
        self.y = self.player_index * self.height
        frame.add_widget(self)

    def move_to_track(self, track_square: TrackSquare):
        frame = track_square.unit_frame
        self.remove_from_parent()
        self.set_size(hx=0.4, hy=0.5)
        x_offset = self.unit_index * frame.width / 30
        match self.player_index:
            case 0:
                self.pos = x_offset, 0
            case 1:
                self.pos = x_offset + frame.width / 2, 0
            case 2:
                self.pos = x_offset + frame.width / 2, frame.height / 2
            case 3:
                self.pos = x_offset, frame.height / 2
        frame.add_widget(self)

    def remove_from_parent(self):
        if self.parent:
            self.parent.remove_widget(self)


class DiceBox(kx.XAnchor):
    def __init__(self, player_index):
        super().__init__()
        self.set_size(hx=0.35, hy=0.1)
        self.color = PLAYER_COLORS[player_index]
        self.frame = kx.XBox()
        self.add_widget(kx.pwrap(self.frame))

    def set_dice(self, dice: list[int], highlight: bool, highlight_die: Optional[int]):
        if highlight:
            self.make_bg(kx.XColor.white())
            self.frame.make_bg(self.color)
        else:
            self.make_bg(kx.XColor.black())
            self.frame.make_bg(self.color.modified_value(0.5))
        self.frame.clear_widgets()
        for i, die in enumerate(dice):
            label = kx.XLabel(
                text=str(die),
                enable_theming=False,
                bold=True,
                color=[1, 1, 1] if highlight else [0.5, 0.5, 0.5],
                outline_width="3sp",
                font_size="30sp",
            )
            if i == highlight_die:
                label.make_bg(kx.XColor.black())
            self.frame.add_widget(kx.pwrap(label))
        while len(self.frame.children) < logic.DICE_COUNT:
            self.frame.add_widget(kx.XAnchor())
