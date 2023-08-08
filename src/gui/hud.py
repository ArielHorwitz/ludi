import itertools

import kvex as kx

import game
from config import DICE_IMAGES_DIR, PLAYER_COLORS

DICE_IMAGES = [
    DICE_IMAGES_DIR / f"die{i}.png" for i in range(game.ROLL_MIN, game.ROLL_MAX + 1)
]
DICE_IMAGES = tuple(path if path.exists() else None for path in DICE_IMAGES)


class Hud(kx.XAnchor):
    def __init__(self, player_index: int):
        super().__init__()
        self.player_index = player_index
        self.color = PLAYER_COLORS[player_index]
        self.main_frame = kx.XBox(orientation="vertical")
        self.main_frame.make_bg(self.color.modified_value(0.5))
        # Spawn
        self.spawnbox = [kx.XAnchor() for uindex in range(game.UNIT_COUNT)]
        spawnbox = kx.XBox()
        spawnbox.add_widgets(*self.spawnbox)
        spawnbox.make_bg(kx.XColor.black().modified_alpha(0.5))
        spawnbox = kx.pwrap(spawnbox)
        # Dicebox
        self.dice_sprites = [kx.kv.Image() for i in range(game.DICE_COUNT)]
        self.dice_labels = [
            kx.XLabel(
                enable_theming=False,
                bold=True,
                font_size="30sp",
                outline_width="3sp",
            )
            for i in range(game.DICE_COUNT)
        ]
        dicebox = kx.XBox()
        for sprite, label in zip(self.dice_sprites, self.dice_labels):
            frame = kx.XAnchor()
            frame.add_widgets(sprite, label)
            dicebox.add_widget(frame)
        dicebox.make_bg(kx.XColor.black().modified_alpha(0.3))
        dicebox = kx.pwrap(dicebox)
        # Label
        self.log_label = kx.XLabel(enable_theming=False, font_size="20sp", italic=True)
        self.progress_label = kx.XLabel(
            enable_theming=False, font_size="25sp", bold=True
        )
        self.progress_label.set_size(x="150sp")
        labelframe = kx.XBox()
        labelframe.set_size(y="30sp")
        labelframe.add_widgets(self.progress_label, self.log_label)
        # Finish line
        self.finishline = [kx.XAnchor() for uindex in range(game.UNIT_COUNT)]
        finishbox = kx.XBox()
        finishbox.add_widgets(*self.finishline)
        self.finish_label = kx.XLabel(
            text="Complete a circle around the track",
            enable_theming=False,
            color=(0, 0, 0),
            font_size="20sp",
        )
        self.finish_label.make_bg(self.color.modified_value(0.5))
        finishline = kx.pwrap(self.finish_label)
        finishline.make_bg(self.color)
        finishline.add_widget(finishbox)
        finishline = kx.pwrap(finishline)
        # Assemble
        self.add_widget(kx.pwrap(self.main_frame))
        widgets = [spawnbox, dicebox, finishline, labelframe]
        if player_index in (0, 3):  # Flip order for top huds to mirror vertically
            widgets = reversed(widgets)
        self.main_frame.add_widgets(*widgets)

    def add_to_spawnbox(self, index, sprite):
        remove_from_parent(sprite)
        self.spawnbox[index].add_widget(sprite)

    def add_to_finishline(self, index, sprite):
        remove_from_parent(sprite)
        self.finishline[index].add_widget(sprite)
        self.finish_label.text = ""

    def set_winner(self):
        for unit_frame in self.finishline:
            remove_from_parent(unit_frame)
        self.finish_label.text = "Winner!"
        self.finish_label.font_size = "50sp"

    def update(self, state: game.GameState, highlight_dice: list[int]):
        # Collect data
        current_index = state.get_player().index
        player = state.players[self.player_index]
        highlight = player.index == current_index
        progress = player.get_progress()
        turns_since = (current_index - player.index) % game.PLAYER_COUNT
        has_last_turn = (log_index := -1 - turns_since) >= -len(state.log)
        last_turn = state.log[log_index] if has_last_turn else ""
        label_color = (0, 0, 0) if highlight else (1, 1, 1)
        # Apply
        self.make_bg(kx.XColor() if highlight else kx.XColor(a=0))
        self.main_frame.make_bg(self.color.modified_value(0.75 if highlight else 0.15))
        self.progress_label.text = f"{progress * 100:.1f}%"
        self.progress_label.color = label_color
        self.log_label.color = label_color
        self.log_label.text = last_turn[3:] if last_turn else ""
        for i, die_value in itertools.zip_longest(range(game.DICE_COUNT), player.dice):
            highlight = i in highlight_dice
            sprite = self.dice_sprites[i]
            label = self.dice_labels[i]
            image_source = None if die_value is None else DICE_IMAGES[die_value - 1]
            saturated_color = self.color.modified_saturation(0.7)
            sprite_color = kx.XColor() if highlight else saturated_color
            invis = kx.XColor(a=0)
            if die_value is None:
                sprite.color = invis.rgba
                label.make_bg(invis)
                label.text = ""
                continue
            if image_source is None:
                sprite.color = invis.rgba
                label.make_bg(sprite_color)
                label.text = str(die_value)
            else:
                sprite.color = sprite_color.rgba
                sprite.source = str(image_source)
                label.make_bg(invis)
                label.text = ""


def remove_from_parent(widget):
    if widget.parent:
        widget.parent.remove_widget(widget)
