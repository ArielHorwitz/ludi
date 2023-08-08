from functools import partial
from typing import Optional

import kvex as kx
import pgnet
from loguru import logger

import config
import game
from tokenizer import EventType, tokenize_turn

from .hud import Hud
from .unit import UnitSprite


class GameWidget(kx.XAnchor):
    def __init__(self, client: pgnet.Client, **kwargs):
        logger.info("Creating game GUI...")
        super().__init__(**kwargs)
        self.state_hash = None
        self.state = game.GameState.new_game()
        self.player_names = set()
        self.chosen_die: Optional[int] = None
        self.__refresh_trigger = kx.create_trigger(
            self._full_refresh,
            timeout=config.GUI_REFRESH_TIMEOUT,
        )
        self.client = client
        self._make_widgets()
        logger.info("Widgets created.")
        hotkeys = self.app.game_controller
        hotkeys.register("force refresh", "^ f5", self._full_refresh)
        set_botspeed = self._user_set_bot_play_interval
        hotkeys.register("speed+ bots", "-", partial(set_botspeed, 0.5))
        hotkeys.register("speed- bots", "=", partial(set_botspeed, -0.5))
        hotkeys.register("leave", "^ escape", self.client.leave_game)
        hotkeys.register("roll", "spacebar", self._user_roll)
        hotkeys.register("roll", "`")
        hotkeys.register("roll", "escape")
        for i in range(max(game.UNIT_COUNT, game.DICE_COUNT)):
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
        self.state = game.GameState.from_json(state)
        logger.debug(f"New game state ({hash(self.state)})")
        last_event = tokenize_turn(self.state.log[-1])[-1]
        if last_event == EventType.TURN_START and len(self.state.log) > 1:
            prev_event = tokenize_turn(self.state.log[-2])[-1]
            config.play_event_sfx(prev_event)
        else:
            if self.state.winner is None:
                config.play_event_sfx(last_event)
            else:
                config.play_victory_sfx()
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
        for i in range(game.TRACK_SIZE):
            track_square = TrackSquare(i)
            track_square.set_size(hx=0.95, hy=0.95)
            self.track_squares.append(track_square)
            track_frame = kx.wrap(track_square)
            self.track_frames.append(track_frame)
            self.track_frame.add_widget(track_frame)
        # Player units and huds
        for pindex in range(game.PLAYER_COUNT):
            sprites = [UnitSprite(pindex, uindex) for uindex in range(game.UNIT_COUNT)]
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
        square_x = width / (game.BOARD_SIZE + 1)
        square_y = height / (game.BOARD_SIZE + 1)
        self.center_frame.set_size(x=width - square_x * 2, y=height - square_y * 2)
        for i, frame in enumerate(self.track_frames):
            frame.set_size(square_x, square_y)
            quarter = i // game.BOARD_SIZE
            offset = i % game.BOARD_SIZE
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
            hud = self.huds[player.index]
            highlight = player.index == current_index
            progress = player.get_progress()
            selected_die = self.chosen_die if highlight else None
            turns_since = (current_index - player.index) % game.PLAYER_COUNT
            has_last_turn = (log_index := -1 - turns_since) >= -len(self.state.log)
            last_turn = self.state.log[log_index] if has_last_turn else ""
            hud.set(highlight, progress, player.dice, selected_die, last_turn)
            for unit, sprite in reversed(list(zip(player.units, sprites))):
                sprite.pulse.start() if highlight else sprite.pulse.stop()
                if unit.position == game.Position.FINISH:
                    sprite.set_size(hx=0.9, hy=0.9)
                    sprite.fade_finish()
                    hud.add_to_finishline(sprite.unit_index, sprite)
                elif unit.position == game.Position.SPAWN:
                    sprite.set_size(hx=0.5, hy=0.5)
                    hud.add_to_spawnbox(sprite.unit_index, sprite)
                elif unit.position == game.Position.TRACK:
                    if sprite.parent:
                        sprite.parent.remove_widget(sprite)
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
        if current_index == self.state.winner:
            self.huds[current_index].set_winner()

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
        self.label = kx.XLabel(
            text=str(position % game.BOARD_SIZE),
            enable_theming=False,
        )
        color = config.PLAYER_COLORS[position // game.BOARD_SIZE]
        if position in game.STARTING_POSITIONS:
            color = color.modified_value(0.5)
            self.label.text = ""
        elif position in game.STAR_POSITIONS:
            color = color.modified_saturation(0.5).modified_value(0.4)
        else:
            color = color.modified_value(0.075)
        self.add_widgets(self.label, self.unit_frame)
        self.make_bg(color)
