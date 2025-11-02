from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

Position = Tuple[int, int]


@dataclass
class Reactor:
    position: Position
    capacity: int
    energy: int = 0

    def deposit(self, amount: int) -> int:
        if amount <= 0 or self.is_full():
            return 0
        accepted = min(amount, self.capacity - self.energy)
        self.energy += accepted
        return accepted

    def draw(self, amount: int) -> int:
        if amount <= 0:
            return 0
        drained = min(amount, self.energy)
        self.energy -= drained
        return drained

    def level_ratio(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return max(0.0, min(1.0, self.energy / self.capacity))

    def is_full(self) -> bool:
        return self.energy >= self.capacity

    def is_empty(self) -> bool:
        return self.energy <= 0


__all__ = ["Reactor"]
