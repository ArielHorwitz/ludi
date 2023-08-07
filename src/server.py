from typing import Optional
import pgnet
import kvex as kx
from pgnet import Packet, Response, Status
import logic
import time

BOT_PLAY_INTERVAL = 2


class GameServer(pgnet.Game):
    def __init__(self, *args, save_string: Optional[str] = None, **kwargs):
        self.state = (
            logic.GameState.new_game()
            if save_string is None
            else logic.GameState.from_json(save_string)
        )
        self.connected_players = set()
        self.human_players = [None] * logic.PLAYER_COUNT
        self.next_bot_play: Optional[float] = None
        self.heartbeat_rate = 2
        super().__init__(*args, **kwargs)
        kx.kv.App.get_running_app().set_theme("midnight")

    @property
    def persistent(self):
        return self.state.turn > 0 and self.state.winner is None

    def get_save_string(self) -> str:
        return self.state.to_json()

    def user_joined(self, player: str):
        if player in self.connected_players:
            return
        self.connected_players.add(player)
        if None in self.human_players:
            index = self.human_players.index(None)
            self.human_players[index] = player
            print(f"Joined as {self.state.players[index].name}: {player}")
        else:
            print(f"Spectating: {player}")

    def user_left(self, player: str):
        if player not in self.connected_players:
            return
        self.connected_players.remove(player)

    def is_bot(self, player_index: int):
        return self.human_players[player_index] is None

    # Logic
    def update(self):
        if not self.is_bot(self.state.get_player().index):
            self.next_bot_play = None
            return
        if self.next_bot_play is None:
            self.next_bot_play = time.time() + BOT_PLAY_INTERVAL
        elif self.next_bot_play < time.time():
            self.state.play_bot()
            self.next_bot_play = time.time() + BOT_PLAY_INTERVAL

    def handle_heartbeat(self, packet: Packet) -> Response:
        state_hash = hash(self.state)
        client_hash = packet.payload.get("state_hash")
        if client_hash == state_hash:
            payload = dict(state_hash=state_hash)
            return Response("Up to date.", payload)
        state = self.state.to_json()
        payload = dict(
            state_hash=state_hash,
            state=state,
        )
        return Response("Updated state.", payload)

    def handle_game_packet(self, packet: Packet) -> Response:
        if self.state.winner is not None:
            return Response("Game is over.", status=Status.UNEXPECTED)
        if packet.username != self.human_players[self.state.get_player().index]:
            return Response("Not your turn.", status=Status.UNEXPECTED)
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
        if self.state.roll_dice():
            return Response("Ok")
        return Response("Roll failed", status=Status.UNEXPECTED)

    def _user_move(self, packet: Packet) -> Response:
        unit_index = int(packet.payload.get("unit_index", -1))
        die_index = int(packet.payload.get("die_index", -1))
        if self.state.move_unit(unit_index, die_index):
            return Response("Ok")
        return Response("Move failed", status=Status.UNEXPECTED)
