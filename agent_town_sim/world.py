from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from .agent import Agent
from .config import DEBUG_MODE
from .models import Act, Action, AgentID, Position
from .reactor import Reactor

Move = Tuple[int, int]
CARDINAL_MOVES: List[Move] = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]


@dataclass
class World:
    width: int = 16  # Grid width in cells for the world.
    height: int = 12  # Grid height in cells for the world.
    tick: int = 0  # Simulation tick counter.
    agents: Dict[AgentID, Agent] = field(default_factory=dict)  # Active agents keyed by ID.
    debug: bool = DEBUG_MODE  # Toggle verbose logging for world events.
    max_energy: int = 200  # Maximum energy stored in a single resource node.
    energy_regen_rate: float = 0.0  # Legacy regen knob; kept for compatibility but unused.
    agent_energy_decay: int = 1  # Energy drained from each agent every tick.
    min_gather_amount: int = 1  # Minimum energy agents prefer before gathering.
    resource_density: float = 0.002  # Probability of spawning a resource on world generation.
    reactor_capacity: int = 1000  # Maximum energy the central reactor can store.
    reactor_initial_energy: int = 200  # Starting energy inside the reactor.
    reactor_agent_reserve: int = 80  # Energy agents keep after donating to avoid shutdown.
    reactor_dwindle_rate: int = 1  # Global drain applied to resources when the reactor is empty.
    reactor_consumption_rate: int = 1  # Fuel the reactor burns automatically each tick.
    aid_request_threshold: int = 40  # Energy level that triggers a help request.
    aid_give_buffer: int = 10  # Extra energy donors keep in addition to their reserve.
    aid_request_lifetime: int = -1  # Negative disables automatic expiry of requests.
    aid_give_min_amount: int = 5  # Minimum energy a donor aims to transfer when helping.
    help_signal_duration: int = -1  # Negative disables automatic expiry of helper highlights.
    energy_grid: List[List[int]] = field(init=False, repr=False)
    resource_grid: List[List[bool]] = field(init=False, repr=False)
    occupancy: Dict[Position, AgentID] = field(init=False, repr=False, default_factory=dict)
    reactor: Reactor = field(init=False, repr=False)
    deposit_reports: List[Tuple[int, AgentID, int, int, bool]] = field(default_factory=list, repr=False)
    help_requests: Dict[AgentID, Tuple[Position, int, int]] = field(default_factory=dict, repr=False)
    helper_signals: Dict[AgentID, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.energy_grid = []
        self.resource_grid = []
        self.occupancy = {}
        self.help_requests = {}
        self.helper_signals = {}
        for _ in range(self.height):
            energy_row: List[int] = []
            resource_row: List[bool] = []
            for _ in range(self.width):
                has_resource = random.random() < max(0.0, min(1.0, self.resource_density))
                resource_row.append(has_resource)
                if has_resource:
                    energy_value = self.max_energy
                    energy_row.append(energy_value)
                else:
                    energy_row.append(0)
            self.energy_grid.append(energy_row)
            self.resource_grid.append(resource_row)
        cx, cy = self.width // 2, self.height // 2
        initial_energy = max(0, min(self.reactor_initial_energy, self.reactor_capacity))
        self.reactor = Reactor(position=(cx, cy), capacity=self.reactor_capacity, energy=initial_energy)
        if self.in_bounds(cx, cy):
            self.resource_grid[cy][cx] = False
            self.energy_grid[cy][cx] = 0

    def add_agent(self, agent: Agent) -> None:
        x, y = agent.position
        agent.position = self._clamp(x, y)
        agent.position = self._ensure_free_position(agent.position)
        self.agents[agent.id] = agent
        self.occupancy[agent.position] = agent.id
        if self.debug:
            self.log(f"Added agent {agent.id} at {agent.position}")

    def log(self, message: str) -> None:
        if self.debug:
            print(f"[Tick {self.tick:04d}] {message}")

    def _clamp(self, x: int, y: int) -> Position:
        return max(0, min(self.width - 1, x)), max(0, min(self.height - 1, y))

    def _occupant(self, x: int, y: int) -> Optional[AgentID]:
        return self.occupancy.get((x, y))

    def is_occupied(self, x: int, y: int) -> bool:
        return self._occupant(x, y) is not None

    def _ensure_free_position(self, position: Position) -> Position:
        x, y = position
        if not self.is_occupied(x, y):
            return position
        for ny in range(self.height):
            for nx in range(self.width):
                if not self.is_occupied(nx, ny):
                    return nx, ny
        raise RuntimeError("World is fully occupied; cannot place agent.")

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def cell_energy(self, x: int, y: int) -> int:
        if not self.in_bounds(x, y):
            return 0
        return self.energy_grid[y][x]

    def visible_energy(self, center: Position, radius: int) -> List[Tuple[Position, int]]:
        cx, cy = center
        visible: List[Tuple[Position, int]] = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius:
                    continue
                nx, ny = cx + dx, cy + dy
                if not self.in_bounds(nx, ny):
                    continue
                visible.append(((nx, ny), self.energy_grid[ny][nx]))
        return visible

    def reactor_position(self) -> Position:
        return self.reactor.position

    def reactor_level_ratio(self) -> float:
        return self.reactor.level_ratio()

    def reactor_needs_energy(self) -> bool:
        return not self.reactor.is_full()

    def active_help_requests(self) -> Dict[AgentID, Tuple[Position, int]]:
        self._prune_help_requests()
        requests: Dict[AgentID, Tuple[Position, int]] = {}
        for agent_id, entry in list(self.help_requests.items()):
            snapshot = self._request_entry(agent_id)
            if snapshot is None:
                continue
            position, amount, _ = snapshot
            requests[agent_id] = (position, amount)
        return requests

    def has_active_request(self, agent_id: AgentID) -> bool:
        self._prune_help_requests()
        return self._request_entry(agent_id) is not None

    def is_recent_helper(self, agent_id: AgentID) -> bool:
        last_tick = self.helper_signals.get(agent_id)
        if last_tick is None:
            return False
        return self.tick - last_tick <= max(0, self.help_signal_duration)

    def available_moves(self, agent: Agent) -> List[Move]:
        x, y = agent.position
        moves = []
        for dx, dy in CARDINAL_MOVES:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                if dx == 0 and dy == 0:
                    moves.append((dx, dy))
                    continue
                occupant = self._occupant(nx, ny)
                if occupant is None:
                    moves.append((dx, dy))
        return moves or [(0, 0)]

    def apply(self, action: Action) -> None:
        agent = self.agents.get(action.actor)
        if agent is None:
            return
        if action.kind is Act.MOVE:
            dx = int(action.params.get("dx", 0))
            dy = int(action.params.get("dy", 0))
            self._move(agent, dx, dy)
        elif action.kind is Act.GATHER:
            self._gather_energy(agent)
        elif action.kind is Act.DEPOSIT:
            self._deposit_energy(agent)
        elif action.kind is Act.REPORT:
            amount = int(action.params.get("amount", 0))
            self._record_deposit_report(agent, amount)
        elif action.kind is Act.REQUEST:
            amount = int(action.params.get("amount", 0))
            self._register_help_request(agent, amount)
        elif action.kind is Act.GIVE:
            target = action.params.get("target")
            amount = int(action.params.get("amount", 0))
            if isinstance(target, str):
                self._give_energy(agent, target, amount)

    def move_agent(self, agent_id: AgentID, dx: int, dy: int) -> None:
        agent = self.agents.get(agent_id)
        if agent is None:
            return
        self._move(agent, dx, dy)

    def _move(self, agent: Agent, dx: int, dy: int) -> None:
        x, y = agent.position
        nx, ny = x + dx, y + dy
        if not self.in_bounds(nx, ny):
            nx, ny = self._clamp(nx, ny)
        if (nx, ny) == (x, y):
            return
        occupant = self._occupant(nx, ny)
        if occupant is not None and occupant != agent.id:
            if self.debug:
                self.log(f"{agent.name} blocked by {occupant} at {(nx, ny)}")
            return
        self.occupancy.pop((x, y), None)
        self.occupancy[(nx, ny)] = agent.id
        agent.position = (nx, ny)
        self._update_request_position(agent)
        if self.debug and (dx or dy):
            self.log(f"{agent.name} moved to {agent.position}")
        self._auto_deposit(agent)

    def _gather_energy(self, agent: Agent) -> None:
        x, y = agent.position
        available = self.cell_energy(x, y)
        if available <= 0:
            return
        collected = available
        self.energy_grid[y][x] = 0
        agent.energy += collected
        self._maybe_clear_help_request(agent)
        if self.debug:
            self.log(f"{agent.name} gathered {collected} energy (total {agent.energy})")
        self._deplete_resource((x, y))

    def _deposit_energy(self, agent: Agent) -> None:
        if agent.position != self.reactor.position:
            return
        excess = max(0, agent.energy - self.reactor_agent_reserve)
        if excess <= 0:
            return
        deposit_amount = excess
        if deposit_amount <= 0 and excess > 0:
            deposit_amount = 1
        deposited = self.reactor.deposit(deposit_amount)
        if deposited <= 0:
            return
        agent.energy -= deposited
        agent.pending_report += deposited
        if self.debug:
            self.log(
                f"{agent.name} deposited {deposited} energy into reactor (level {self.reactor.energy})"
            )

    def _record_deposit_report(self, agent: Agent, amount: int) -> None:
        pending_before = agent.pending_report
        claimed = max(0, amount)
        if pending_before <= 0 and claimed <= 0:
            return
        actual = min(pending_before, claimed) if pending_before > 0 else 0
        if pending_before > 0:
            agent.pending_report = max(0, pending_before - actual)
        lie = claimed != actual
        self.deposit_reports.append((self.tick, agent.id, actual, claimed, lie))
        if len(self.deposit_reports) > 50:
            self.deposit_reports.pop(0)
        if self.debug:
            honesty = "honest" if not lie else "dishonest"
            self.log(
                f"{agent.name} reported depositing {claimed} energy "
                f"(credited {actual}, {honesty})"
            )

    def _auto_deposit(self, agent: Agent) -> None:
        if agent.position != self.reactor.position:
            return
        self._deposit_energy(agent)

    def _register_help_request(self, agent: Agent, amount: int) -> None:
        threshold = max(self.aid_request_threshold, self.agent_energy_decay)
        desired_default = max(0, threshold - agent.energy)
        if agent.max_capacity is None:
            capacity_headroom: Optional[int] = None
        else:
            capacity_headroom = max(0, agent.max_capacity - agent.energy)
        request_cap = max(0, amount) if capacity_headroom is None else min(max(0, amount), capacity_headroom)
        requested = max(desired_default, request_cap)
        if requested <= 0:
            return
        self.help_requests[agent.id] = (agent.position, requested, self.tick)
        if self.debug:
            self.log(f"{agent.name} requested {requested} energy from nearby allies")

    def _update_request_position(self, agent: Agent) -> None:
        entry = self.help_requests.get(agent.id)
        if entry is None:
            return
        _, amount, tick = entry
        self.help_requests[agent.id] = (agent.position, amount, tick)

    def _maybe_clear_help_request(self, agent: Agent) -> None:
        entry = self.help_requests.get(agent.id)
        if entry is None:
            return
        position, amount, tick_logged = entry
        threshold = max(self.aid_request_threshold, self.agent_energy_decay)
        if agent.energy > threshold:
            self.help_requests.pop(agent.id, None)
            return
        capacity_headroom = None
        if agent.max_capacity is not None:
            capacity_headroom = max(0, agent.max_capacity - agent.energy)
        shortfall = threshold - agent.energy
        if shortfall < 0:
            shortfall = 0
        if capacity_headroom is not None:
            shortfall = min(shortfall, capacity_headroom)
        desired = shortfall
        if desired <= 0:
            self.help_requests.pop(agent.id, None)
        else:
            self.help_requests[agent.id] = (position, desired, self.tick)

    def _clear_help_request(self, agent_id: AgentID) -> None:
        self.help_requests.pop(agent_id, None)

    def cancel_help_request(self, agent_id: AgentID) -> None:
        self._clear_help_request(agent_id)

    def _request_entry(self, agent_id: AgentID) -> Optional[Tuple[Position, int, int]]:
        entry = self.help_requests.get(agent_id)
        if entry is None:
            return None
        position, amount, tick_logged = entry
        if amount <= 0:
            return None
        if agent_id not in self.agents:
            return None
        if self.aid_request_lifetime > 0 and self.tick - tick_logged > self.aid_request_lifetime:
            return None
        return position, amount, tick_logged

    def _prune_help_requests(self) -> None:
        stale = [
            agent_id
            for agent_id, entry in self.help_requests.items()
            if self._request_entry(agent_id) is None
        ]
        for agent_id in stale:
            self.help_requests.pop(agent_id, None)

    def _decay_helper_signals(self) -> None:
        if self.help_signal_duration < 0:
            return
        expiry = max(0, self.help_signal_duration)
        expired = [
            agent_id
            for agent_id, tick_logged in self.helper_signals.items()
            if self.tick - tick_logged > expiry
        ]
        for agent_id in expired:
            self.helper_signals.pop(agent_id, None)

    def _give_energy(self, donor: Agent, target_id: AgentID, amount: int) -> None:
        recipient = self.agents.get(target_id)
        if recipient is None or recipient.id == donor.id:
            return
        dx = recipient.position[0] - donor.position[0]
        dy = recipient.position[1] - donor.position[1]
        if max(abs(dx), abs(dy)) > 1:
            return
        retain_floor = max(0, self.reactor_agent_reserve)
        give_buffer = max(0, self.aid_give_buffer)
        min_amount = max(1, self.aid_give_min_amount)
        eligible_energy = donor.energy - (retain_floor + give_buffer)
        if eligible_energy <= 0:
            return
        request_entry = self._request_entry(recipient.id)
        requested_remaining = request_entry[1] if request_entry else max(0, amount)
        desired_transfer = max(min_amount, max(0, amount))
        capacity_room: Optional[int]
        if recipient.max_capacity is None:
            capacity_room = None
        else:
            capacity_room = max(0, recipient.max_capacity - recipient.energy)
        limits = [eligible_energy, desired_transfer, requested_remaining]
        if capacity_room is not None:
            limits.append(capacity_room)
        transfer_capacity = min(limits)
        if transfer_capacity <= 0:
            return
        donor.energy -= transfer_capacity
        recipient.energy += transfer_capacity
        if request_entry:
            _, outstanding, _ = request_entry
            updated_amount = max(0, outstanding - transfer_capacity)
            if updated_amount > 0:
                self.help_requests[recipient.id] = (recipient.position, updated_amount, self.tick)
            else:
                self._clear_help_request(recipient.id)
        self._maybe_clear_help_request(recipient)
        self.helper_signals[donor.id] = self.tick
        if self.debug:
            self.log(
                f"{donor.name} transferred {transfer_capacity} energy to {recipient.name}"
            )

    def _deplete_resource(self, position: Position) -> None:
        x, y = position
        self.energy_grid[y][x] = 0
        self.resource_grid[y][x] = False
        self._respawn_resource(position)

    def _respawn_resource(self, depleted_position: Position) -> None:
        candidates = [
            (cx, cy)
            for cy in range(self.height)
            for cx in range(self.width)
            if not self.resource_grid[cy][cx] and (cx, cy) != depleted_position
        ]
        if candidates:
            target = random.choice(candidates)
        else:
            target = depleted_position
        tx, ty = target
        self.resource_grid[ty][tx] = True
        self.energy_grid[ty][tx] = self.max_energy
        if self.debug:
            self.log(f"Resource respawned at {(tx, ty)} with {self.max_energy} energy")

    def _dwindle_resources(self, amount: int) -> None:
        if amount <= 0:
            return
        for y, row in enumerate(self.energy_grid):
            for x, value in enumerate(row):
                if value <= 0:
                    continue
                new_value = max(0, value - amount)
                row[x] = new_value
                if new_value <= 0 and self.resource_grid[y][x]:
                    self.resource_grid[y][x] = False

    def _consume_reactor_energy(self) -> None:
        if self.reactor_consumption_rate <= 0:
            return
        self.reactor.draw(self.reactor_consumption_rate)

    def _apply_reactor_consequences(self) -> None:
        if not self.reactor.is_empty():
            return
        if self.debug:
            self.log("Reactor depleted; resources dwindling")
        self._dwindle_resources(self.reactor_dwindle_rate)

    def _decay_agent_energy(self) -> None:
        if self.agent_energy_decay <= 0:
            return
        to_remove: List[AgentID] = []
        for agent_id, agent in list(self.agents.items()):
            current_energy = agent.energy
            next_energy = max(0, current_energy - self.agent_energy_decay)
            agent.energy = next_energy
            if next_energy <= 0:
                to_remove.append(agent_id)
        for agent_id in to_remove:
            agent = self.agents.pop(agent_id, None)
            if agent is None:
                continue
            self.occupancy.pop(agent.position, None)
            self.help_requests.pop(agent_id, None)
            self.helper_signals.pop(agent_id, None)
            if self.debug:
                self.log(f"Removed agent {agent.id} at {agent.position} (energy depleted)")

    def step(self) -> None:
        self.tick += 1
        self._prune_help_requests()
        self._decay_helper_signals()
        for agent in list(self.agents.values()):
            self._auto_deposit(agent)
            action = agent.choose(self)
            agent.pending_action = action
        for agent in list(self.agents.values()):
            action = agent.pending_action
            if action is None:
                continue
            self.apply(action)
            agent.pending_action = None
        self._decay_agent_energy()
        self._consume_reactor_energy()
        self._apply_reactor_consequences()

    def agent_positions(self) -> Dict[AgentID, Position]:
        return {agent_id: agent.position for agent_id, agent in self.agents.items()}

    def deposit_history(self) -> List[Tuple[int, AgentID, int, int, bool]]:
        return list(self.deposit_reports)


__all__ = ["World", "CARDINAL_MOVES"]
