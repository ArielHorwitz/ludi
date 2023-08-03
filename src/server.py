import pgnet
import kvex as kx
from pgnet import Packet, Response, Status
from logic import GameState


class GameServer(pgnet.Game):
    def __init__(self, *args, **kwargs):
        self.state = GameState.new_game()
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
        if self.state.winner is not None:
            return Response("Game is over.", status=Status.UNEXPECTED)
        method_name = f"_user_{packet.message}"
        if not hasattr(self, method_name):
            return Response(
                f"No such command: `{packet.message}`",
                status=Status.UNEXPECTED,
            )
        method = getattr(self, method_name)
        return method(packet)

    # User commands
    def _user_roll(self, packet: Packet) -> Response:
        return Response(self.state.roll_dice())

    def _user_move(self, packet: Packet) -> Response:
        unit_index = int(packet.payload.get("unit_index", -1))
        die_index = int(packet.payload.get("die_index", -1))
        return Response(self.state.move_unit(unit_index, die_index))
