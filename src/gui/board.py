from functools import partial
from typing import Optional

import kvex as kx
import pgnet
from loguru import logger

import config
import game
from tokenizer import EventType, tokenize_turn

from .animation import Animation, Interp
from .hud import Hud
from .unit import UnitSprite


class GameWidget(kx.XAnchor):
    def __init__(self, client: pgnet.Client, **kwargs):
        logger.info("Creating game GUI...")
        super().__init__(**kwargs)
        self.state_hash = None
        self.state = game.GameState.new_game()
        self.player_names = set()
        self.selected_unit: Optional[int] = None
        self.selected_die: Optional[int] = None
        self.__refresh_trigger = kx.create_trigger(
            self._full_refresh,
            timeout=config.GUI_REFRESH_TIMEOUT,
        )
        self.client = client
        self._make_widgets()
        logger.info("Widgets created.")
        hotkeys = self.app.game_controller
        hotkeys.register("force refresh", "^ f5", self._full_refresh)
        hotkeys.register("leave", "^ escape", self.client.leave_game)
        hotkeys.register("proceed", "spacebar", self._proceed)
        hotkeys.register("cancel", "escape", self._cancel)
        for i in range(max(game.UNIT_COUNT, game.DICE_COUNT)):
            control = keynumber = str(i + 1)
            hotkeys.register(control, keynumber)  # Number keys
            hotkeys.register(control, f"f{keynumber}")  # F keys
            hotkeys.bind(control, partial(self._select, i))
        hotkeys.register("spectate", "^+ s", self._spectate)
        hotkeys.register("speed+ bots", "-", partial(self._set_bot_speed, 0.5))
        hotkeys.register("speed- bots", "=", partial(self._set_bot_speed, -0.5))
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
                config.play_sfx(config.VICTORY_SFX)
        self._clear_selections()
        self._refresh_widgets()

    def heartbeat_payload(self) -> str:
        return dict(state_hash=hash(self.state))

    def _on_response(self, response: pgnet.Response):
        logger.debug(response)

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
        # Resolve selection highlights
        turn_player = self.state.get_player()
        turn_index = turn_player.index
        rolled = not turn_player.missing_dice
        unit_selected = self.selected_unit is not None
        die_selected = self.selected_die is not None
        highlight_squares = []
        highlight_units = []
        highlight_dice = []
        match rolled, unit_selected, die_selected:
            case True, True, True:
                highlight_units = [self.selected_unit]
                highlight_dice = [self.selected_die]
                die_value = turn_player.dice[self.selected_die]
                unit = turn_player.units[self.selected_unit]
                highlight_squares = [unit.get_position(add_distance=die_value)]
            case True, True, True:
                highlight_units = [self.selected_unit]
                highlight_dice = [self.selected_die]
            case True, True, False:
                unit = turn_player.units[self.selected_unit]
                highlight_units = [self.selected_unit]
                highlight_dice = [
                    i for i, d in enumerate(turn_player.dice) if unit.can_use_die(d)
                ]
            case True, False, _:
                highlight_units = turn_player.movable_units
        logger.debug(f"{self.selected_unit=} {highlight_units=}")
        logger.debug(f"{self.selected_die=} {highlight_dice=}")
        logger.debug(f"{highlight_squares=}")
        # Apply loop
        for player, sprites in zip(self.state.players, self.unit_sprites):
            my_turn = player.index == turn_index
            hud = self.huds[player.index]
            hud.update(self.state, highlight_dice if my_turn else [])
            for unit, sprite in reversed(list(zip(player.units, sprites))):
                highlight = my_turn and unit.index in highlight_units
                sprite.pulse.start() if highlight else sprite.pulse.stop()
                if unit.finished:
                    sprite.set_size(hx=0.9, hy=0.9)
                    sprite.fade_finish()
                    hud.add_to_finishline(sprite.unit_index, sprite)
                elif unit.in_spawn:
                    sprite.set_size(hx=0.5, hy=0.5)
                    hud.add_to_spawnbox(sprite.unit_index, sprite)
                else:
                    assert unit.on_track
                    self.track_squares[unit.position].add_unit(sprite)
        for i, square in enumerate(self.track_squares):
            square.pulse.start() if i in highlight_squares else square.pulse.stop()
        if turn_index == self.state.winner:
            self.huds[turn_index].set_winner()

    def _proceed(self):
        if self.state.get_player().missing_dice:
            self.client.send(pgnet.Packet("roll"), self._on_response)
            self._clear_selections()
            self._refresh_widgets()
        elif self.selected_unit is not None and self.selected_die is not None:
            payload = dict(
                unit_index=self.selected_unit,
                die_index=self.selected_die,
            )
            self.client.send(pgnet.Packet("move", payload), self._on_response)

    def _cancel(self):
        config.play_sfx(config.UI_CLICK2)
        self.client.flush_queue()
        self._clear_selections()
        self._refresh_widgets()

    def _select(self, index: int):
        player = self.state.get_player()
        if player.missing_dice:
            logger.debug("cannot select when missing rolls")
            return
        if self.selected_unit is None:
            if index in player.movable_units:
                self.selected_unit = index
                self.selected_die = None
                config.play_sfx(config.UI_CLICK1)
                logger.debug(f"selected unit: {index}")
            else:
                logger.debug(f"cannot select unit: {index}")
        elif self.selected_die is None:
            unit = player.units[self.selected_unit]
            valid_index = 0 <= index < len(player.dice)
            if valid_index and unit.can_use_die(player.dice[index]):
                self.selected_die = index
                config.play_sfx(config.UI_CLICK1)
                logger.debug(f"selected die: {index}")
            else:
                logger.debug(f"cannot select die: {index}")
        else:
            logger.debug("already selected")
        self._refresh_widgets()

    def _clear_selections(self, *a):
        self.selected_unit = None
        self.selected_die = None

    def _set_bot_speed(self, delta):
        payload = dict(delta=delta)
        self.client.send(
            pgnet.Packet("set_bot_play_interval", payload), self._on_response
        )

    def _spectate(self):
        self.client.send(pgnet.Packet("spectate"), self._on_response)


class TrackSquare(kx.XAnchor):
    def __init__(self, position: int):
        super().__init__()
        self.position = position
        self.color = config.PLAYER_COLORS[position // game.BOARD_SIZE]
        self.unit_frame = kx.XRelative()
        self.label = kx.XLabel(
            text=str(position % game.BOARD_SIZE),
            enable_theming=False,
        )
        if position in game.STARTING_POSITIONS:
            self.label.text = ""
        self.add_widgets(self.label, self.unit_frame)
        self.make_bg(self._get_bg_color())
        self.pulse = Animation(
            self._pulse,
            Interp.pulse,
            speed=3,
            end_callback=self._end_pulse,
        )

    def add_unit(self, sprite: UnitSprite):
        if sprite.parent:
            sprite.parent.remove_widget(sprite)
        sprite.set_size(hx=0.4, hy=0.5)
        x_offset = sprite.unit_index * self.width / 30
        sprite.pos = [
            (x_offset, 0),
            (x_offset + self.width / 2, 0),
            (x_offset + self.width / 2, self.height / 2),
            (x_offset, self.height / 2),
        ][sprite.player_index]
        self.unit_frame.add_widget(sprite)

    def _get_bg_color(self):
        if self.position in game.STARTING_POSITIONS:
            return self.color.modified_value(0.5)
        elif self.position in game.STAR_POSITIONS:
            return self.color.modified_saturation(0.5).modified_value(0.4)
        else:
            return self.color.modified_value(0.075)

    def _pulse(self, modulated: float):
        self.make_bg(self.color.modified_value(0.5).modified_saturation(modulated))

    def _end_pulse(self):
        self.make_bg(self._get_bg_color())
