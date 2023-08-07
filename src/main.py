"""Ludi game built on top of MouseFox."""

from pathlib import Path
from functools import partial
import pgnet
import os
os.environ["KIVY_LOG_MODE"] = "PYTHON"
from server import GameServer  # noqa: E402
from gui import GameWidget  # noqa: E402

SAVE_FILE = Path.home() / ".ludi.save"
INFO_TEXT = (
    "[b][u]Welcome to Ludi[/u][/b]" "\n\n" "A game inspired by the classic Ludo."
)
ONLINE_INFO_TEXT = (
    "[u]Connecting to a server[/u]"
    "\n\n"
    "To register (if the server allows it) simply choose a username and password"
    " and log in."
)
APP_CONFIG = dict(
    game_class=GameServer,
    game_widget=GameWidget,
    server_factory=partial(pgnet.Server, save_file=SAVE_FILE),
    title="Ludi",
    info_text=INFO_TEXT,
    online_info_text=ONLINE_INFO_TEXT,
)


def run():
    """Run Ludi."""
    from mousefox import run

    run(**APP_CONFIG)


if __name__ == "__main__":
    run()
