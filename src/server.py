import pgnet
import kvex as kx
from pgnet import Packet, Response
from logic import (
    GameState,
    Track,
    PLAYER_COUNT,
    TRACK_SIZE,
    STARTING_POSITIONS,
    get_dice_roll,
)


class GameServer(pgnet.Game):
    def __init__(self, *args, **kwargs):
        self.state = GameState()
        self.player_names = set()
        self.heartbeat_rate = 2
        super().__init__(*args, **kwargs)
        kx.kv.App.get_running_app().set_theme("midnight")

    @property
    def persistent(self):
        return False

    def get_save_string(self) -> str:
        return self.state.to_json()

    def user_joined(self, player: str):
        print(f"Joined: {player}")
        self.player_names.add(player)

    def user_left(self, player: str):
        print(f"Left: {player}")
        self.player_names.remove(player)

    # Logic
    def update(self):
        pass

    def handle_heartbeat(self, packet: Packet) -> Response:
        state_hash = hash(self.state)
        client_hash = packet.payload.get("state_hash")
        if client_hash == state_hash:
            payload = dict(state_hash=state_hash, player_names=tuple(self.player_names))
            return Response("Up to date.", payload)
        state = self.state.to_json()
        payload = dict(
            state_hash=state_hash,
            state=state,
            player_names=tuple(self.player_names),
        )
        return Response("Updated state.", payload)

    def handle_game_packet(self, packet: Packet) -> Response:
        method_name = f"_user_{packet.message}"
        if not hasattr(self, method_name):
            self._autoplay()
            return Response(f"No such command: `{packet.message}`")
        method = getattr(self, method_name)
        return method(packet)

    def _autoplay(self):
        player_idx = self.state.turn % PLAYER_COUNT
        player = self.state.players[player_idx]
        for unit in player.units:
            if unit.track != Track.END:
                break
        if unit.track == Track.START:
            unit.track = Track.MAIN
            unit.position = STARTING_POSITIONS[player_idx]
        elif unit.track == Track.MAIN:
            unit.position += get_dice_roll()
            if unit.position - STARTING_POSITIONS[player_idx] >= TRACK_SIZE:
                unit.track = Track.END
        self.state.turn += 1

    # User commands
    def _user_autoplay(self, packet: Packet) -> Response:
        turn = self.state.turn
        self._autoplay()
        return Response(f"Played turn {turn}")
