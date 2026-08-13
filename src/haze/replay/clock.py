"""Virtual clock for replay mode.

The demo must be reproducible on every take of a recording, so the API does not
use wall-clock time. It holds a virtual clock positioned inside the scenario
window; every endpoint answers "as of" that instant. Seeking is instantaneous
and playback advances the clock at a configurable multiple of real time.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from .. import config


class ReplayClock:
    """Thread-safe virtual clock. Advances only while `playing` is True."""

    def __init__(
        self,
        start: str = config.SCENARIO_START,
        end: str = config.SCENARIO_END,
        speed: float = config.DEFAULT_REPLAY_SPEED,
    ) -> None:
        self._start = config.parse_ts(start)
        self._end = config.parse_ts(end)
        self._speed = speed
        self._playing = False
        self._lock = threading.Lock()

        default = config.bookmark(config.DEFAULT_BOOKMARK)
        self._virtual = config.parse_ts(default["timestamp"]) if default else self._start
        self._anchor_real = time.monotonic()

    # -- internals ---------------------------------------------------------
    def _now_locked(self) -> datetime:
        """Current virtual time, advancing it if playback is running."""
        if self._playing:
            elapsed = time.monotonic() - self._anchor_real
            self._virtual = self._virtual + timedelta(seconds=elapsed * self._speed)
            self._anchor_real = time.monotonic()
            if self._virtual >= self._end:
                self._virtual = self._end
                self._playing = False
        return self._virtual

    def _set_locked(self, dt: datetime) -> None:
        self._virtual = min(max(dt, self._start), self._end)
        self._anchor_real = time.monotonic()

    # -- public API --------------------------------------------------------
    def now(self) -> datetime:
        with self._lock:
            return self._now_locked()

    def now_iso(self) -> str:
        return config.iso(self.now())

    def seek(self, timestamp: str) -> datetime:
        with self._lock:
            self._set_locked(config.parse_ts(timestamp))
            return self._virtual

    def seek_bookmark(self, key: str) -> datetime | None:
        bm = config.bookmark(key)
        if bm is None:
            return None
        return self.seek(bm["timestamp"])

    def play(self, speed: float | None = None) -> None:
        with self._lock:
            self._now_locked()  # settle current position before changing state
            if speed is not None:
                self._speed = speed
            if self._virtual >= self._end:
                self._set_locked(self._start)
            self._playing = True
            self._anchor_real = time.monotonic()

    def pause(self) -> None:
        with self._lock:
            self._now_locked()
            self._playing = False

    def reset(self) -> None:
        """Return to the default bookmark, paused. Used between recording takes."""
        with self._lock:
            self._playing = False
            default = config.bookmark(config.DEFAULT_BOOKMARK)
            self._set_locked(
                config.parse_ts(default["timestamp"]) if default else self._start
            )
            self._speed = config.DEFAULT_REPLAY_SPEED

    def state(self) -> dict:
        with self._lock:
            now = self._now_locked()
            return {
                "clock": config.iso(now),
                "start": config.iso(self._start),
                "end": config.iso(self._end),
                "speed": self._speed,
                "playing": self._playing,
            }
