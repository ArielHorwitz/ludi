import dataclasses
import math
import time
from typing import Any, Callable, Optional

import kvex as kx

from config import ANIMATION_FPS


@dataclasses.dataclass
class Continuous:
    callback: Callable[[float], None]
    duration: Optional[float] = None
    speed: float = 1
    guarantee_last: Optional[float] = None
    end_callback: Optional[Callable[[], None]] = None
    start_time: float = 0
    scheduled: Optional[Any] = None

    def __post_init__(self):
        assert callable(self._get_value)

    @property
    def active(self) -> bool:
        return self.scheduled is not None

    def start(self, *args):
        self.stop()
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
        self.callback(self._get_value(elapsed))


@dataclasses.dataclass
class Linear(Continuous):
    def _get_value(self, elapsed: float) -> float:
        value = elapsed * self.speed
        return value / self.duration if self.duration else value


@dataclasses.dataclass
class Pulse(Continuous):
    def _get_value(self, elapsed: float) -> float:
        return math.fabs(math.sin(elapsed * self.speed))
