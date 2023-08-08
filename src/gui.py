from typing import Optional
from pathlib import Path
import itertools
import random
import kvex as kx
import pgnet
import logic
import tokenizer
from loguru import logger
from tokenizer import EventType
from functools import partial


DEFAULT_VOLUME = 0.5
PLAYER_COLORS = (
    kx.XColor.from_name("blue"),
    kx.XColor.from_name("green"),
    kx.XColor.from_name("yellow"),
    kx.XColor.from_name("red"),
)
ASSET_DIR = Path(__file__).parent / "assets"
DICE_IMAGES_DIR = ASSET_DIR / "images" / "dice"
DICE_IMAGES = [
    DICE_IMAGES_DIR / f"die{i}.png" for i in range(logic.ROLL_MIN, logic.ROLL_MAX + 1)
]
DICE_IMAGES = tuple(path if path.exists() else None for path in DICE_IMAGES)
print(DICE_IMAGES)
DICE_SFX_DIR = ASSET_DIR / "sfx" / "dice"
DICE_SFX = tuple(kx.SoundLoader.load(str(f)) for f in (DICE_SFX_DIR).iterdir())
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
    sfx.volume = DEFAULT_VOLUME
    sfx.play()


class GameWidget(kx.XAnchor):
    def __init__(self, client: pgnet.Client, **kwargs):
        logger.info("Creating game GUI...")
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
        logger.info("Widgets created.")
        hotkeys = self.app.game_controller
        hotkeys.register("force refresh", "^ f5", self._full_refresh)
        hotkeys.register(
            "slow down bots", "-", partial(self._user_set_bot_play_interval, 0.5)
        )
        hotkeys.register(
            "speed up bots", "=", partial(self._user_set_bot_play_interval, -0.5)
        )
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
        logger.info("Game GUI created.")

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
        self.track_frames = []
        self.track_squares = []
        self.unit_sprites = []
        self.huds = []
        self.track_frame = kx.XRelative()
        self.center_frame = kx.XGrid(cols=2)
        self.add_widgets(self.track_frame, self.center_frame)
        # Track
        for i in range(logic.TRACK_SIZE):
            track_square = TrackSquare(i)
            track_square.set_size(hx=0.95, hy=0.95)
            self.track_squares.append(track_square)
            track_frame = kx.wrap(track_square)
            self.track_frames.append(track_frame)
            self.track_frame.add_widget(track_frame)
        # Player units and huds
        for pindex in range(logic.PLAYER_COUNT):
            sprites = [UnitSprite(pindex, uindex) for uindex in range(logic.UNIT_COUNT)]
            self.unit_sprites.append(sprites)
            hud = Hud(pindex)
            self.huds.append(hud)
        # Add huds in correct order (clockwise from bottom-left)
        for pindex in (1, 2, 0, 3):
            self.center_frame.add_widget(self.huds[pindex])

    def _trigger_refresh(self, *args):
        kx.snooze_trigger(self.__refresh_trigger)

    def _full_refresh(self, *args):
        self._refresh_geometry()
        kx.schedule_once(self._refresh_widgets)

    def _refresh_geometry(self, *args):
        width = self.width
        height = self.height
        square_x = width / (logic.BOARD_SIZE + 1)
        square_y = height / (logic.BOARD_SIZE + 1)
        self.center_frame.set_size(x=width - square_x * 2, y=height - square_y * 2)
        for i, frame in enumerate(self.track_frames):
            frame.set_size(square_x, square_y)
            quarter = i // logic.BOARD_SIZE
            offset = i % logic.BOARD_SIZE
            if quarter == 0:
                frame.x = 0
                frame.y = square_y * offset
            elif quarter == 1:
                frame.x = square_x * offset
                frame.y = height - square_y
            elif quarter == 2:
                frame.x = width - square_x
                frame.y = height - square_y * (offset + 1)
            elif quarter == 3:
                frame.x = width - square_x * (offset + 1)
                frame.y = 0
            else:
                raise RuntimeError(f"not a valid quarter {i=} {quarter=} {frame=}")

    def _refresh_widgets(self, *args):
        player = self.state.get_player()
        current_index = player.index
        for player, sprites in zip(self.state.players, self.unit_sprites):
            highlight = player.index == current_index
            selected_die = self.chosen_die if highlight else None
            hud = self.huds[player.index]
            hud.set(highlight, player.dice, selected_die)
            starting_square = self.track_squares[logic.STARTING_POSITIONS[player.index]]
            starting_square.label.text = f"{round(100 * player.get_progress(), 1)}%"
            for unit, sprite in reversed(list(zip(player.units, sprites))):
                remove_from_parent(sprite)
                if unit.position == logic.Position.FINISH:
                    sprite.set_size(hx=0.9, hy=0.9)
                    sprite.fade_finish()
                    hud.add_to_finishline(sprite.unit_index, sprite)
                elif unit.position == logic.Position.SPAWN:
                    sprite.set_size(hx=0.5, hy=0.5)
                    hud.add_to_spawnbox(sprite.unit_index, sprite)
                elif unit.position == logic.Position.TRACK:
                    sprite.set_size(hx=0.4, hy=0.5)
                    unit_pos = unit.get_position(player.index)
                    frame = self.track_squares[unit_pos].unit_frame
                    x_offset = unit.index * frame.width / 30
                    sprite.pos = [
                        (x_offset, 0),
                        (x_offset + frame.width / 2, 0),
                        (x_offset + frame.width / 2, frame.height / 2),
                        (x_offset, frame.height / 2),
                    ][player.index]
                    frame.add_widget(sprite)

                else:
                    raise RuntimeError(f"unregocnized {unit.position=}")

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
            color = color.modified_saturation(0.5).modified_value(0.4)
        else:
            color = color.modified_value(0.075)
        self.add_widgets(self.label, self.unit_frame)
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

    def fade_finish(self):
        color = PLAYER_COLORS[self.player_index]
        self.make_bg(color.modified_saturation(0).modified_value(0.5))


class Hud(kx.XAnchor):
    def __init__(self, player_index: int):
        super().__init__()
        self.color = PLAYER_COLORS[player_index]
        self.main_frame = kx.XBox(orientation="vertical")
        self.main_frame.make_bg(self.color.modified_value(0.5))
        # Spawn
        self.spawnbox = [kx.XAnchor() for uindex in range(logic.UNIT_COUNT)]
        spawnbox = kx.XBox()
        spawnbox.add_widgets(*self.spawnbox)
        spawnbox.make_bg(kx.XColor.black().modified_alpha(0.5))
        # Dicebox
        self.dice_sprites = [kx.kv.Image() for i in range(logic.DICE_COUNT)]
        self.dice_labels = [
            kx.XLabel(
                enable_theming=False,
                bold=True,
                font_size="30sp",
                outline_width="3sp",
            )
            for i in range(logic.DICE_COUNT)
        ]
        dicebox = kx.XBox()
        for sprite, label in zip(self.dice_sprites, self.dice_labels):
            frame = kx.XAnchor()
            frame.add_widgets(sprite, label)
            dicebox.add_widget(frame)
        dicebox.make_bg(kx.XColor.black().modified_alpha(0.3))
        # Finish line
        self.finishline = [kx.XAnchor() for uindex in range(logic.UNIT_COUNT)]
        finishbox = kx.XBox()
        finishbox.add_widgets(*self.finishline)
        self.finish_label = kx.XLabel(
            text="Finish Line", color=(0, 0, 0), font_size="30sp"
        )
        self.finish_label.make_bg(self.color.modified_value(0.5))
        finishline = kx.pwrap(self.finish_label)
        finishline.make_bg(self.color)
        finishline.add_widget(finishbox)
        # Assemble
        self.add_widget(kx.pwrap(self.main_frame))
        widgets = [kx.pwrap(spawnbox), kx.pwrap(dicebox), kx.pwrap(finishline)]
        if player_index in (1, 2):  # Flip order for top huds to mirror vertically
            widgets = reversed(widgets)
        self.main_frame.add_widgets(*widgets)

    def add_to_spawnbox(self, index, sprite):
        self.spawnbox[index].add_widget(sprite)

    def add_to_finishline(self, index, sprite):
        self.finishline[index].add_widget(sprite)
        self.finish_label.text = ""

    def set(
        self,
        highlight: bool,
        dice: list[int],
        selected_die: Optional[int],
    ):
        self.make_bg(kx.XColor() if highlight else kx.XColor(a=0))
        self.main_frame.make_bg(self.color.modified_value(0.5 if highlight else 0.2))
        for i, die_value in itertools.zip_longest(range(logic.DICE_COUNT), dice):
            sprite = self.dice_sprites[i]
            label = self.dice_labels[i]
            image_source = None if die_value is None else DICE_IMAGES[die_value - 1]
            selected = i == selected_die
            saturated_color = self.color.modified_saturation(0.7).rgb
            invis = kx.XColor(a=0)
            match die_value is not None, image_source is not None:
                case True, True:
                    sprite.color = (1, 1, 1) if selected else saturated_color
                    sprite.source = str(image_source)
                    label.make_bg(invis)
                    label.text = ""
                case True, False:
                    sprite.color = invis.rgba
                    label.make_bg(saturated_color if selected else kx.XColor())
                    label.text = str(die_value)
                case False, _:
                    sprite.color = invis.rgba
                    label.make_bg(invis)
                    label.text = ""


def remove_from_parent(widget):
    if widget.parent:
        widget.parent.remove_widget(widget)
