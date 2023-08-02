import kvex as kx
import pgnet
import math
from logic import GameState, BOARD_SIZE, Track, UNIT_COUNT, TRACK_SIZE


BOARD_END = BOARD_SIZE - 1
assert BOARD_SIZE % 2 == 0
BOARD_MIDDLE = (BOARD_END) / 2
assert BOARD_MIDDLE != int(BOARD_MIDDLE)
SPAWNS = (
    (1, 1),
    (1, BOARD_END - 1),
    (BOARD_END - 1, BOARD_END - 1),
    (BOARD_END - 1, 1),
)
COMPLETED = (
    (math.floor(BOARD_MIDDLE), math.floor(BOARD_MIDDLE)),
    (math.floor(BOARD_MIDDLE), math.ceil(BOARD_MIDDLE)),
    (math.ceil(BOARD_MIDDLE), math.ceil(BOARD_MIDDLE)),
    (math.ceil(BOARD_MIDDLE), math.floor(BOARD_MIDDLE)),
)


def _track_to_coords(track_position: int) -> (int, int):
    track_position %= TRACK_SIZE
    quarter = track_position // (BOARD_SIZE)
    offset = track_position % (BOARD_SIZE)
    if quarter == 0:
        return 0, offset
    elif quarter == 1:
        return offset, BOARD_END
    elif quarter == 2:
        return BOARD_END, BOARD_END - offset
    elif quarter == 3:
        return BOARD_END - offset, 0
    else:
        raise RuntimeError(
            f"Track position {track_position} not on track {quarter=} {offset=}"
        )


class GameWidget(kx.XFrame):
    def __init__(self, client: pgnet.Client, **kwargs):
        """Override base method."""
        self.state_hash = None
        self.state = GameState()
        self.player_names = set()
        self.last_rolls = list()
        self.server_response = "Awaiting request."
        super().__init__(**kwargs)
        self.client = client
        self._make_widgets()
        self.app.game_controller.register("leave", "^ escape", self.client.leave_game)
        self.app.game_controller.register("autoplay", "spacebar", self._user_autoplay)
        client.on_heartbeat = self.on_heartbeat
        client.heartbeat_payload = self.heartbeat_payload

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
        self.last_rolls = heartbeat_response.payload.get("last_rolls")
        print(f"New game state ({hash(self.state)})")
        self._refresh_widgets()

    def heartbeat_payload(self) -> str:
        return dict(state_hash=hash(self.state))

    def _on_response(self, response: pgnet.Response):
        self.server_response = response
        self._refresh_widgets()

    def _make_widgets(self):
        # Info panel
        self.info_panel = kx.XLabel(halign="left", valign="top")
        panel_frame = kx.pwrap(self.info_panel)
        panel_frame.set_size(x="350dp")
        # Board
        self.board_buttons = []
        board_frame = kx.XGrid(cols=BOARD_SIZE)
        for x in range(BOARD_SIZE):
            self.board_buttons.append([])
            for y in range(BOARD_SIZE):
                btn = kx.XButton(
                    subtheme_name="primary",
                    on_release=lambda *a, c=(x, y): self._invoke_board_button(*c),
                )
                self.board_buttons[-1].append(btn)
                board_frame.add_widget(kx.pwrap(btn))
        # Assemble
        main_frame = kx.XBox()
        main_frame.add_widgets(panel_frame, board_frame)
        self.clear_widgets()
        self.add_widget(main_frame)

    def _refresh_widgets(self, *args):
        # Update info panel
        fg2 = self.subtheme.fg2.markup
        player_names = "\n".join(f"- {name}" for name in self.player_names)
        self.info_panel.text = "\n".join(
            [
                "\n",
                fg2("[u][b]Game[/b][/u]"),
                self.client.game,
                "\n",
                fg2("[u][b]Info[/b][/u]"),
                f"Last rolls: {self.last_rolls}",
                f"Turn: {self.state.turn}",
                f"Players: {len(self.player_names)}",
                player_names,
                "\n",
                fg2("[i][b]Server says:[/b][/i]"),
                str(self.server_response),
            ]
        )
        # Update buttons
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                btn = self.board_buttons[x][y]
                btn.text = ""
                if 0 < x < BOARD_END and 0 < y < BOARD_END:
                    btn.subtheme_name = "primary"
                else:
                    btn.subtheme_name = "secondary"
        for player_idx, player in enumerate(self.state.players):
            for rev_unit_idx, unit in enumerate(reversed(player.units)):
                unit_idx = UNIT_COUNT - rev_unit_idx - 1
                accent = False
                if unit.track == Track.MAIN:
                    x, y = _track_to_coords(unit.position)
                    accent = True
                elif unit.track == Track.START:
                    x, y = SPAWNS[player_idx]
                elif unit.track == Track.END:
                    x, y = COMPLETED[player_idx]
                else:
                    raise RuntimeError(f"Unexpected unit.track value: {unit.track}")
                text = f"\n{{[b]{player_idx}[/b]}} {unit_idx}"
                btn = self.board_buttons[x][y]
                btn.text += text
                if accent:
                    btn.subtheme_name = "accent"

    def _user_autoplay(self):
        self.client.send(pgnet.Packet("autoplay"), self._on_response)

    def _invoke_board_button(self, x: int, y: int):
        print(f"button: {x},{y}")
