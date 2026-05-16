from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RecordingEdge(Enum):
    STARTED = auto()
    STOPPED = auto()


@dataclass(frozen=True)
class RecordingSignals:
    arrangement: int
    session_status: int

    @property
    def active(self) -> bool:
        return self.arrangement == 1 or self.session_status != 0


@dataclass
class RecordingStateMachine:
    """Tracks combined arrangement + session recording; emits start/stop edges."""

    was_active: bool = False

    def apply(self, signals: RecordingSignals) -> list[RecordingEdge]:
        edges: list[RecordingEdge] = []
        is_active = signals.active

        if is_active and not self.was_active:
            edges.append(RecordingEdge.STARTED)
        elif not is_active and self.was_active:
            edges.append(RecordingEdge.STOPPED)

        self.was_active = is_active
        return edges

    def sync_initial(self, signals: RecordingSignals) -> list[RecordingEdge]:
        """On boot: if already recording, emit STARTED once."""
        if signals.active and not self.was_active:
            self.was_active = True
            return [RecordingEdge.STARTED]
        self.was_active = signals.active
        return []
