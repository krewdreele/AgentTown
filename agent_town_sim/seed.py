from __future__ import annotations

import random
from typing import Iterable

from .agent import Agent
from .world import World


def seed_world(
    agent_count: int = 4,
    width: int = 64,
    height: int = 48,
    debug: bool = False,
    id_prefix: str = "A",
) -> World:
    world = World(width=width, height=height, debug=debug)
    occupied: set[tuple[int, int]] = set()
    for index in range(agent_count):
        x, y = _random_empty_cell(width, height, occupied)
        occupied.add((x, y))
        agent_id = f"{id_prefix}{index:02d}"
        agent = Agent(id=agent_id, name=f"Agent {index}", position=(x, y))
        world.add_agent(agent)
    return world


def _random_empty_cell(width: int, height: int, occupied: Iterable[tuple[int, int]]) -> tuple[int, int]:
    occupied_set = set(occupied)
    free_cells = [
        (x, y)
        for x in range(width)
        for y in range(height)
        if (x, y) not in occupied_set
    ]
    if not free_cells:
        return 0, 0
    return random.choice(free_cells)


__all__ = ["seed_world"]
