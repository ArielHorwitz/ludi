import dataclasses
import math
import time
from typing import Any, Callable, Optional

import kvex as kx

from config import ANIMATION_FPS


class Interp:
    @staticmethod
    def linear(anim: "Animation", elapsed: float) -> float:
        value = elapsed * anim.speed
        return value / anim.duration if anim.duration else value

    @staticmethod
    def pulse(anim: "Animation", elapsed: float) -> float:
        return math.fabs(math.sin(elapsed * anim.speed))

    @staticmethod
    def flat(anim: "Animation", elapsed: float) -> float:
        return anim.speed


@dataclasses.dataclass
class Animation:
    callback: Callable[[float], None]
    interpolation: Callable[["Animation", float], float] = Interp.linear
    duration: Optional[float] = None
    speed: float = 1
    guarantee_last: Optional[float] = None
    start_callback: Optional[Callable[[], None]] = None
    end_callback: Optional[Callable[[], None]] = None
    start_time: float = 0
    scheduled: Optional[Any] = None

    @property
    def active(self) -> bool:
        return self.scheduled is not None

    def start(self, *args):
        self.stop()
        if self.start_callback is not None:
            self.start_callback()
        self.start_time = time.time()
        self.scheduled = kx.schedule_interval(self._event, 1 / ANIMATION_FPS)

    def stop(self, *args):
        was_active = self.active
        if was_active:
            self.scheduled.cancel()
            self.scheduled = None
        if was_active and self.guarantee_last is not None:
            self.callback(self.guarantee_last)
        if was_active and self.end_callback is not None:
            self.end_callback()

    def _event(self, *args):
        assert self.active
        assert self.speed > 0
        elapsed = time.time() - self.start_time
        duration = self.duration
        if duration is not None and elapsed >= duration:
            self.stop()
            return
        self.callback(self.interpolation(self, elapsed))
