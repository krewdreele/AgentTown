from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Tuple

AgentID = str
Position = Tuple[int, int]


class Act(Enum):
    MOVE = auto()
    GATHER = auto()
    DEPOSIT = auto()
    REPORT = auto()
    REQUEST = auto()
    GIVE = auto()


@dataclass
class Action:
    kind: Act
    actor: AgentID
    params: Dict[str, int] = field(default_factory=dict)


__all__ = ["AgentID", "Position", "Act", "Action"]
