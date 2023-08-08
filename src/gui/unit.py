import kvex as kx

import game
from config import ASSET_DIR, PLAYER_COLORS

from .animation import Pulse


class UnitSprite(kx.XAnchor):
    def __init__(self, player_index: int, unit_index: int):
        super().__init__()
        self.player_index = player_index
        self.unit_index = unit_index
        self.color = PLAYER_COLORS[self.player_index].modified_value(0.5)
        self.make_bg(self.color, ASSET_DIR / "unit.png")
        self.pulse = Pulse(self._pulse, speed=3, guarantee_last=1)
        self.label = kx.XLabel(
            text=game.UNIT_NAMES[unit_index],
            enable_theming=False,
            color=(0, 0, 0),
            outline_color=(1, 1, 1),
            outline_width="2sp",
            bold=True,
            font_size="30sp",
        )
        self.add_widget(self.label)

    def fade_finish(self):
        self.make_bg(self.color.modified_saturation(0))

    def _pulse(self, modulated: float):
        self.make_bg(self.color.modified_saturation(modulated))
