from typing import Optional
from pathlib import Path
import random
import kvex as kx
import pgnet
from logic import (
    GameState,
    TRACK_SIZE,
    BOARD_SIZE,
    DICE_COUNT,
    UNIT_COUNT,
    Position,
)
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
UNIT_NAMES = "ABCDEFGHIJ"
ASSET_DIR = Path(__file__).parent / "assets"
DICE_SFX = tuple(kx.SoundLoader.load(str(f)) for f in (ASSET_DIR / "dice").iterdir())


def play_dice_sfx():
    sfx = random.choice(DICE_SFX)
    if sfx.get_pos():
        sfx.stop()
    sfx.play()


class GameWidget(kx.XFrame):
    def __init__(self, client: pgnet.Client, **kwargs):
        """Override base method."""
        self.state_hash = None
        self.state = GameState()
        self.player_names = set()
        self.chosen_die: Optional[int] = None
        self.server_response = pgnet.Response("Awaiting request.")
        super().__init__(**kwargs)
        self.client = client
        self._make_widgets()
        hotkeys = self.app.game_controller
        hotkeys.register("leave", "^ escape", self.client.leave_game)
        hotkeys.register("roll", "spacebar", self._user_roll)
        for i in range(max(UNIT_COUNT, DICE_COUNT)):
            control = keynumber = str(i + 1)
            hotkeys.register(control, keynumber)  # Number keys
            hotkeys.register(control, f"f{keynumber}")  # F keys
            hotkeys.bind(control, partial(self._select_index, i))
        client.on_heartbeat = self.on_heartbeat
        client.heartbeat_payload = self.heartbeat_payload
        self._on_geometry()

    def on_subtheme(self, *args, **kwargs):
        super().on_subtheme(*args, **kwargs)
        self._refresh_widgets()

    def on_heartbeat(self, heartbeat_response: pgnet.Response):
        self.player_names = heartbeat_response.payload["player_names"]
        state = heartbeat_response.payload.get("state")
        if state is None:
            self._refresh_widgets()
            return
        self.state = GameState.from_json(state)
        print(f"New game state ({hash(self.state)})")
        self._refresh_widgets()

    def heartbeat_payload(self) -> str:
        return dict(state_hash=hash(self.state))

    def _on_response(self, response: pgnet.Response):
        self.server_response = response
        self.chosen_die = None
        self._refresh_widgets()

    def _make_widgets(self):
        self.clear_widgets()
        # Info panel
        self.info_panel = kx.XLabel(halign="left", valign="top")
        panel_frame = kx.pwrap(self.info_panel)
        panel_frame.set_size(x="200sp")
        # Board
        self.track_squares = []
        self.board_frame = kx.XRelative()
        self.spawn_frame = kx.XRelative()
        self.spawn_frame.set_size(hx=0.3, hy=0.3)
        for i in range(TRACK_SIZE):
            track_square = TrackSquare(i // BOARD_SIZE, i % BOARD_SIZE)
            if i % BOARD_SIZE == 0:
                track_square.make_starting()
            self.board_frame.add_widget(track_square)
            self.track_squares.append(track_square)
        self.board_frame.bind(size=self._on_geometry)
        self.unit_sprites = []
        self.dice_boxes = []
        self.dice_frame = kx.XAnchor()
        self.dice_frame.set_size(hx=0.8, hy=0.8)
        for player_index, (ax, ay) in enumerate(PLAYER_ANCHORS):
            dicebox = DiceBox(player_index)
            self.dice_frame.add_widget(kx.wrap(dicebox, anchor_x=ax, anchor_y=ay))
            self.dice_boxes.append(dicebox)
            self.unit_sprites.append([])
            for unit_index in range(UNIT_COUNT):
                unit = UnitSprite(player_index, unit_index)
                self.unit_sprites[-1].append(unit)
        # Assemble
        main_frame = kx.XBox()
        board_frame = kx.XAnchor()
        board_frame.add_widgets(self.board_frame, self.spawn_frame, self.dice_frame)
        board_frame.make_bg(kx.XColor(0.3, 0.3, 0.3))
        main_frame.add_widgets(panel_frame, board_frame)
        self.add_widget(main_frame)

    def _on_geometry(self, *args):
        width = self.board_frame.width
        height = self.board_frame.height
        square_x = width / (BOARD_SIZE + 1)
        square_y = height / (BOARD_SIZE + 1)
        for i, square in enumerate(self.track_squares):
            square.set_size(square_x * 0.9, square_y * 0.9)
            quarter = i // BOARD_SIZE
            offset = i % BOARD_SIZE
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
        # Update info panel
        fg2 = self.subtheme.fg2.markup
        hash_repr = str(hash(self.state))[:6]
        player = self.state.get_player()
        player_names = "\n".join(f"- {name}" for name in self.player_names)
        player_dice = "\n".join(
            f"{{{p.index + 1}}} {p.dice}" for p in self.state.players
        )
        player_progress = "\n".join(
            f"{p.get_progress() * 100:.1f} %" for p in self.state.players
        )
        self.info_panel.text = "\n".join(
            [
                "\n",
                fg2("[u][b]Game[/b][/u]"),
                self.client.game,
                hash_repr,
                "\n",
                fg2("[u][b]Info[/b][/u]"),
                f"Turn #{self.state.turn:>3}: {player.index}",
                "Dice:",
                player_dice,
                "\n",
                "Progress:",
                player_progress,
                "\n",
                f"Players: {len(self.player_names)}",
                player_names,
                "\n",
                fg2("[i][b]Server says:[/b][/i]"),
                str(self.server_response.message),
                str(self.server_response.payload),
            ]
        )
        current_index = player.index
        for player, sprites in zip(self.state.players, self.unit_sprites):
            highlight = player.index == current_index
            highlight_die = self.chosen_die if highlight else None
            self.dice_boxes[player.index].set_dice(player.dice, highlight, highlight_die)
            for unit, sprite in reversed(list(zip(player.units, sprites))):
                match unit.position:
                    case Position.FINISH:
                        sprite.remove_from_parent()
                    case Position.SPAWN:
                        sprite.move_to_spawn(self.spawn_frame)
                    case Position.TRACK:
                        square = self.track_squares[unit.get_position(player.index)]
                        sprite.move_to_track(square)

    def _user_roll(self):
        self.client.send(pgnet.Packet("roll"), self._on_roll)
        self._refresh_widgets()

    def _on_roll(self, response: pgnet.Response):
        if not response.status:
            play_dice_sfx()
        self._on_response(response)

    def _select_index(self, index: int):
        if self.chosen_die is None:
            self.chosen_die = index
        else:
            payload = dict(die_index=self.chosen_die, unit_index=index)
            self.client.send(pgnet.Packet("move", payload), self._on_response)
        self._refresh_widgets()


class TrackSquare(kx.XAnchor):
    def __init__(self, quarter: int, offset: int):
        super().__init__()
        self.color = PLAYER_COLORS[quarter]
        value = 0.2 - 0.1 * (offset / (BOARD_SIZE + 1))
        self.make_bg(color=self.color.modified_value(value))
        self.unit_frame = kx.XRelative()
        self.add_widget(self.unit_frame)

    def make_starting(self):
        self.make_bg(color=self.color.modified_value(0.5))


class UnitSprite(kx.XAnchor):
    def __init__(self, player_index: int, unit_index: int):
        super().__init__()
        self.player_index = player_index
        self.unit_index = unit_index
        self.make_bg(color=PLAYER_COLORS[player_index], source=ASSET_DIR / "unit.png")
        self.label = kx.XLabel(text=UNIT_NAMES[unit_index], color=(0, 0, 0), bold=True)
        self.add_widget(self.label)

    def move_to_spawn(self, frame):
        self.remove_from_parent()
        self.set_size(hx=0.25, hy=0.25)
        self.x = self.unit_index * self.width
        self.y = self.player_index * self.height
        frame.add_widget(self)

    def move_to_track(self, track_square: TrackSquare):
        self.remove_from_parent()
        self.set_size(hx=0.5, hy=0.5)
        match self.player_index:
            case 0:
                self.pos = 0, 0
            case 1:
                self.pos = self.width, 0
            case 2:
                self.pos = self.width, self.height
            case 3:
                self.pos = 0, self.height
        track_square.unit_frame.add_widget(self)

    def remove_from_parent(self):
        if self.parent:
            self.parent.remove_widget(self)


class DiceBox(kx.XBox):
    def __init__(self, player_index):
        super().__init__()
        self.set_size(hx=0.35, hy=0.1)
        self.color = PLAYER_COLORS[player_index]
        self.make_bg(self.color)

    def set_dice(self, dice: list[int], highlight: bool, highlight_die: Optional[int]):
        self.clear_widgets()
        if highlight:
            self.make_bg(self.color)
        else:
            self.make_bg(self.color.modified_value(0.2))
        for i, die in enumerate(dice):
            label = kx.XLabel(text=str(die), bold=True, font_size="30sp")
            if i == highlight_die:
                label.make_bg(kx.XColor.black())
            self.add_widget(kx.pwrap(label))
        while len(self.children) < DICE_COUNT:
            self.add_widget(kx.pwrap(kx.XLabel()))

