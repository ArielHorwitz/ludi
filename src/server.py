import time
from typing import Optional

import pgnet
from loguru import logger
from pgnet import Packet, Response, Status

import game

DEFAULT_BOT_PLAY_INTERVAL = 2
MAX_BOT_PLAY_INTERVAL = 10


class GameServer(pgnet.Game):
    def __init__(self, *args, save_string: Optional[str] = None, **kwargs):
        self.state = (
            game.GameState.new_game()
            if save_string is None
            else game.GameState.from_json(save_string)
        )
        self.bot_play_interval = DEFAULT_BOT_PLAY_INTERVAL
        self.connected_players = set()
        self.human_players = [None] * game.PLAYER_COUNT
        self.next_bot_play: Optional[float] = None
        self.heartbeat_rate = 2
        super().__init__(*args, **kwargs)

    @property
    def persistent(self):
        return all(
            (
                self.state.turn > 0,
                self.state.winner is None,
                self._humans_playing,
            )
        )

    @property
    def _humans_playing(self) -> bool:
        return any(p is not None for p in self.human_players)

    def get_save_string(self) -> str:
        return self.state.to_json()

    def user_joined(self, player: str):
        self.connected_players.add(player)
        logger.info(f"Joined: {player}")
        logger.debug(f"Connected players: {self.connected_players}")
        index = self._assign_player(player)
        if index is not None:
            logger.info(f"Playing as {self.state.players[index].name}: {player}")
        else:
            logger.info(f"Spectating: {player}")

    def user_left(self, player: str):
        if player in self.connected_players:
            self.connected_players.remove(player)
        logger.info(f"Left: {player}")
        logger.debug(f"Connected players: {self.connected_players}")

    def _assign_player(self, player) -> Optional[int]:
        if player in self.human_players:
            return self.human_players.index(player)
        if None in self.human_players:
            index = self.human_players.index(None)
            self.human_players[index] = player
            return index
        return None

    def _unassign_player(self, player) -> bool:
        unassigned = False
        while player in self.human_players:
            index = self.human_players.index(player)
            self.human_players[index] = None
            unassigned = True
        return unassigned

    def is_bot(self, player_index: int):
        return self.human_players[player_index] is None

    # Logic
    def update(self):
        if not self.connected_players:
            return
        player = self.state.get_player()
        if self.state.winner is not None:
            return
        if not self.is_bot(player.index):
            self.next_bot_play = None
            return
        if self.next_bot_play is None:
            self.next_bot_play = time.time() + self.bot_play_interval
            return
        if self.next_bot_play > time.time():
            return
        self.state.play_bot()
        self.print_logs()
        self.next_bot_play = time.time() + self.bot_play_interval

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
        method_name = f"_user_{packet.message}"
        if not hasattr(self, method_name):
            return Response(
                f"No such command: `{packet.message}`",
                status=Status.UNEXPECTED,
            )
        method = getattr(self, method_name)
        result = method(packet)
        self.print_logs()
        return result

    def print_logs(self):
        logger.debug(
            "Logs (turn: {self.state.turn}):\n" + "\n".join(self.state.log[-5:])
        )

    # User commands
    def _user_roll(self, packet: Packet) -> Response:
        if packet.username != self.human_players[self.state.get_player().index]:
            return Response("Not your turn.", status=Status.UNEXPECTED)
        if self.state.roll_dice():
            return Response("Ok")
        return Response("Roll failed", status=Status.UNEXPECTED)

    def _user_move(self, packet: Packet) -> Response:
        if packet.username != self.human_players[self.state.get_player().index]:
            return Response("Not your turn.", status=Status.UNEXPECTED)
        unit_index = int(packet.payload.get("unit_index", -1))
        die_index = int(packet.payload.get("die_index", -1))
        if self.state.move_unit(unit_index, die_index):
            return Response("Ok")
        return Response("Move failed", status=Status.UNEXPECTED)

    def _user_set_bot_play_interval(self, packet: Packet) -> Response:
        value = packet.payload.get("interval", DEFAULT_BOT_PLAY_INTERVAL)
        delta = packet.payload.get("delta", 0)
        if delta != 0:
            value = self.bot_play_interval
        self.bot_play_interval = max(0, min(MAX_BOT_PLAY_INTERVAL, value + delta))
        self.next_bot_play = time.time()
        return Response(f"Bot play interval: {self.bot_play_interval}")

    def _user_spectate(self, packet: Packet) -> Response:
        if self._unassign_player(packet.username):
            return Response("Spectating.")
        index = self._assign_player(packet.username)
        if index is not None:
            return Response(f"Rejoined as: {self.state.players[index].name}")
        return Response("Cannot join (game is full?)")
