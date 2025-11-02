from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from .models import Act, Action, AgentID, Position

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from .world import World


@dataclass
class Agent:
    id: AgentID
    name: str
    position: Position
    energy: int = 30
    max_capacity: Optional[int] = None
    vision_radius: int = 100
    pending_action: Optional[Action] = None
    pending_report: int = 0

    def choose(self, world: "World") -> Action:
        x, y = self.position
        moves = world.available_moves(self)
        non_idle_moves = [move for move in moves if move != (0, 0)]

        if self.pending_report > 0:
            return Action(kind=Act.REPORT, actor=self.id, params={"amount": self.pending_report})

        def best_move_towards(target: Position) -> Optional[tuple[int, int]]:
            if target == (x, y):
                return None
            dx_total = target[0] - x
            dy_total = target[1] - y

            def sign(value: int) -> int:
                return 1 if value > 0 else -1

            ordered_candidates: List[tuple[int, int]] = []
            if abs(dx_total) >= abs(dy_total):
                if dx_total != 0:
                    ordered_candidates.append((sign(dx_total), 0))
                if dy_total != 0:
                    ordered_candidates.append((0, sign(dy_total)))
            else:
                if dy_total != 0:
                    ordered_candidates.append((0, sign(dy_total)))
                if dx_total != 0:
                    ordered_candidates.append((sign(dx_total), 0))

            for candidate in ordered_candidates:
                if candidate in moves:
                    return candidate

            best_move: Optional[tuple[int, int]] = None
            best_score: Optional[int] = None
            for dx, dy in moves:
                nx, ny = x + dx, y + dy
                score = abs(nx - target[0]) + abs(ny - target[1])
                if best_score is None or score < best_score:
                    best_score = score
                    best_move = (dx, dy)
            return best_move

        cell_energy = world.cell_energy(x, y)
        decay = max(1, getattr(world, "agent_energy_decay", 1))
        reserve = max(decay, getattr(world, "reactor_agent_reserve", decay))
        request_threshold = max(decay, getattr(world, "aid_request_threshold", reserve))
        give_buffer = max(0, getattr(world, "aid_give_buffer", 0))
        give_min = max(1, getattr(world, "aid_give_min_amount", 1))

        active_requests = getattr(world, "active_help_requests", lambda: {})()
        has_request = getattr(world, "has_active_request", lambda _agent_id: False)
        cancel_request = getattr(world, "cancel_help_request", None)
        already_requested = has_request(self.id)

        visible_cells = world.visible_energy(self.position, self.vision_radius)
        energy_spots = [
            (pos, energy, abs(pos[0] - x) + abs(pos[1] - y))
            for pos, energy in visible_cells
            if energy > 0
        ]
        energy_spots.sort(key=lambda item: (item[2], -item[1]))

        low_on_energy = self.energy <= request_threshold
        shareable_energy = max(0, self.energy - (reserve + give_buffer))
        comfortable_level = reserve + give_buffer + give_min
        needs_energy = low_on_energy or self.energy < comfortable_level

        if already_requested and not low_on_energy and callable(cancel_request):
            cancel_request(self.id)
            already_requested = False

        # Step 1: help nearby agents if we see a request and can spare energy.
        if shareable_energy >= give_min and active_requests:
            request_options: List[tuple[int, int, int, int, AgentID, Position]] = []
            for target_id, (target_pos, target_need) in active_requests.items():
                if target_id == self.id:
                    continue
                dx_req = target_pos[0] - x
                dy_req = target_pos[1] - y
                manhattan_dist = abs(dx_req) + abs(dy_req)
                if manhattan_dist <= self.vision_radius:
                    chebyshev_dist = max(abs(dx_req), abs(dy_req))
                    request_options.append(
                        (manhattan_dist, -target_need, chebyshev_dist, target_need, target_id, target_pos)
                    )
            if request_options:
                request_options.sort(key=lambda entry: (entry[0], entry[1]))
                _, _, adjacency, need, target_id, target_pos = request_options[0]
                if adjacency <= 1:
                    transfer = min(shareable_energy, max(give_min, need))
                    if transfer > 0:
                        return Action(
                            kind=Act.GIVE,
                            actor=self.id,
                            params={"target": target_id, "amount": transfer},
                        )
                if adjacency > 1:
                    move = best_move_towards(target_pos)
                    if move is not None:
                        dx, dy = move
                        return Action(kind=Act.MOVE, actor=self.id, params={"dx": dx, "dy": dy})

        # Step 2: if we still need more energy, prioritise collecting or seeking help.
        if needs_energy:
            reachable_entries = [
                entry
                for entry in energy_spots
                if entry[2] == 0 or self.energy > decay * entry[2]
            ]
            for target_pos, _, target_dist in reachable_entries:
                if target_dist == 0 and cell_energy > 0:
                    return Action(kind=Act.GATHER, actor=self.id)
                move = best_move_towards(target_pos)
                if move is not None:
                    dx, dy = move
                    return Action(kind=Act.MOVE, actor=self.id, params={"dx": dx, "dy": dy})

            request_amount = max(0, request_threshold - self.energy)
            if request_amount > 0 and not already_requested:
                return Action(kind=Act.REQUEST, actor=self.id, params={"amount": request_amount})

            potential_helpers: List[tuple[int, int, AgentID, Position]] = []
            for other_id, other_agent in getattr(world, "agents", {}).items():
                if other_id == self.id:
                    continue
                available = other_agent.energy - (reserve + give_buffer)
                if available < give_min:
                    continue
                dx_helper = other_agent.position[0] - x
                dy_helper = other_agent.position[1] - y
                helper_manhattan = abs(dx_helper) + abs(dy_helper)
                if helper_manhattan <= self.vision_radius:
                    helper_chebyshev = max(abs(dx_helper), abs(dy_helper))
                    potential_helpers.append(
                        (helper_manhattan, helper_chebyshev, other_id, other_agent.position)
                    )
            if potential_helpers:
                potential_helpers.sort(key=lambda entry: (entry[0], entry[1]))
                helper_manhattan, helper_chebyshev, _, helper_pos = potential_helpers[0]
                if helper_chebyshev > 1:
                    move = best_move_towards(helper_pos)
                    if move is not None:
                        dx, dy = move
                        return Action(kind=Act.MOVE, actor=self.id, params={"dx": dx, "dy": dy})

        reactor_pos = world.reactor_position() if hasattr(world, "reactor_position") else None
        reactor_needs_energy = (
            world.reactor_needs_energy() if hasattr(world, "reactor_needs_energy") else True
        )
        excess_energy = max(0, self.energy - reserve)

        # Step 3: deposit to the reactor when we have excess energy.
        if reactor_pos is not None and reactor_needs_energy and excess_energy > 0:
            if self.position == reactor_pos:
                return Action(kind=Act.DEPOSIT, actor=self.id, params={"amount": excess_energy})
            move = best_move_towards(reactor_pos)
            if move is not None:
                dx, dy = move
                return Action(kind=Act.MOVE, actor=self.id, params={"dx": dx, "dy": dy})

        if cell_energy > 0:
            return Action(kind=Act.GATHER, actor=self.id)

        fallback_moves = non_idle_moves or moves or [(0, 0)]
        dx, dy = random.choice(fallback_moves)
        return Action(kind=Act.MOVE, actor=self.id, params={"dx": dx, "dy": dy})


__all__ = ["Agent"]
