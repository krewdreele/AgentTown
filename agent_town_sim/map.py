from __future__ import annotations

from typing import Iterable, Tuple, TYPE_CHECKING

try:
    import pygame  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    pygame = None  # type: ignore

if TYPE_CHECKING:
    from .world import World

BACKGROUND_COLOR: Tuple[int, int, int] = (20, 24, 32)
GRID_LINE_COLOR: Tuple[int, int, int] = (50, 56, 68)
GRID_LINE_HIGHLIGHT: Tuple[int, int, int] = (70, 75, 90)
ENERGY_LOW_COLOR: Tuple[int, int, int] = (32, 38, 48)
ENERGY_HIGH_COLOR: Tuple[int, int, int] = (120, 210, 140)
AGENT_BASE_COLOR: Tuple[int, int, int] = (218, 220, 230)
AGENT_LOW_ENERGY_COLOR: Tuple[int, int, int] = (200, 70, 70)
AGENT_HIGH_ENERGY_COLOR: Tuple[int, int, int] = (130, 224, 140)
AGENT_OUTLINE_COLOR: Tuple[int, int, int] = (18, 22, 30)
HUD_TEXT_COLOR: Tuple[int, int, int] = (235, 235, 235)
HELP_REQUEST_MARKER_COLOR: Tuple[int, int, int] = (255, 110, 110)
HELP_GIVER_MARKER_COLOR: Tuple[int, int, int] = (110, 200, 255)
REACTOR_CELL_BASE: Tuple[int, int, int] = (70, 85, 120)
REACTOR_CELL_FILL: Tuple[int, int, int] = (240, 180, 75)
REACTOR_OUTLINE_COLOR: Tuple[int, int, int] = (255, 220, 140)
REACTOR_BAR_BACKGROUND: Tuple[int, int, int] = (40, 44, 56)
REACTOR_BAR_FILL: Tuple[int, int, int] = (240, 180, 75)


def require_pygame():
    """
    Returns the pygame module if available, otherwise raises a descriptive error.
    """
    if pygame is None:
        raise RuntimeError(
            "pygame is required for rendering. Install it with 'pip install pygame'."
        )
    return pygame


def canvas_size(world: "World", cell_size: int) -> Tuple[int, int]:
    """
    Compute the pixel width/height needed to display the world grid.
    """
    return world.width * cell_size, world.height * cell_size


def _cell_fill_color(world: "World", x: int, y: int) -> Tuple[int, int, int]:
    energy = world.cell_energy(x, y)
    max_energy = getattr(world, "max_energy", 0) or 1
    clamped_energy = max(0, min(energy, max_energy))
    ratio = clamped_energy / max_energy
    return tuple(
        int(low + (high - low) * ratio) for low, high in zip(ENERGY_LOW_COLOR, ENERGY_HIGH_COLOR)
    )


def _agent_energy_ratio(agent) -> float:
    max_capacity = getattr(agent, "max_capacity", None)
    energy = getattr(agent, "energy", 0)
    if max_capacity is None or max_capacity <= 0:
        return 1.0 if energy > 0 else 0.0
    return max(0.0, min(1.0, energy / max_capacity))


def _agent_energy_color(agent) -> Tuple[int, int, int]:
    ratio = _agent_energy_ratio(agent)
    return tuple(
        int(low + (high - low) * ratio)
        for low, high in zip(AGENT_LOW_ENERGY_COLOR, AGENT_HIGH_ENERGY_COLOR)
    )


def draw_world(surface, world: "World", cell_size: int, font=None) -> None:
    """
    Render the grid world onto a pygame surface.
    """
    pg = require_pygame()
    surface.fill(BACKGROUND_COLOR)
    _draw_grid(surface, world, cell_size, pg)
    _draw_reactor(surface, world, cell_size, pg)
    _draw_agents(surface, world, cell_size, pg, font)
    _draw_reactor_meter(surface, world, pg, font)


def _draw_grid(surface, world: "World", cell_size: int, pg) -> None:
    width, height = world.width, world.height
    for x in range(width):
        for y in range(height):
            rect = pg.Rect(x * cell_size, y * cell_size, cell_size, cell_size)
            fill_color = _cell_fill_color(world, x, y)
            pg.draw.rect(surface, fill_color, rect)
            outline_color = GRID_LINE_HIGHLIGHT if (x + y) % 2 == 0 else GRID_LINE_COLOR
            pg.draw.rect(surface, outline_color, rect, width=1)


def _draw_reactor(surface, world: "World", cell_size: int, pg) -> None:
    if not hasattr(world, "reactor_position"):
        return
    reactor_pos = world.reactor_position()
    if not isinstance(reactor_pos, tuple) or len(reactor_pos) != 2:
        return
    rx, ry = reactor_pos
    in_bounds = getattr(world, "in_bounds", None)
    if not callable(in_bounds) or not in_bounds(rx, ry):
        return
    rect = pg.Rect(rx * cell_size, ry * cell_size, cell_size, cell_size)
    pg.draw.rect(surface, REACTOR_CELL_BASE, rect)
    level_ratio = getattr(world, "reactor_level_ratio", lambda: 0.0)()
    level_ratio = max(0.0, min(1.0, level_ratio))
    if level_ratio > 0:
        inner_padding = max(2, cell_size // 6)
        inner_rect = rect.inflate(-inner_padding * 2, -inner_padding * 2)
        fill_height = max(1, int(inner_rect.height * level_ratio))
        fill_rect = pg.Rect(
            inner_rect.left,
            inner_rect.bottom - fill_height,
            inner_rect.width,
            fill_height,
        )
        pg.draw.rect(surface, REACTOR_CELL_FILL, fill_rect)
    pg.draw.rect(surface, REACTOR_OUTLINE_COLOR, rect, width=2)


def _draw_agents(surface, world: "World", cell_size: int, pg, font) -> None:
    radius = max(6, int(cell_size * 0.35))
    agents = sorted(world.agents.values(), key=lambda agent: agent.id)
    for index, agent in enumerate(agents):
        x, y = agent.position
        cx = x * cell_size + cell_size // 2
        cy = y * cell_size + cell_size // 2
        ratio = _agent_energy_ratio(agent)
        indicator_color = _agent_energy_color(agent)
        pg.draw.circle(surface, AGENT_BASE_COLOR, (cx, cy), radius)
        indicator_radius = max(2, int(radius * ratio)) if ratio > 0 else max(2, radius // 4)
        pg.draw.circle(surface, indicator_color, (cx, cy), indicator_radius)
        pg.draw.circle(surface, AGENT_OUTLINE_COLOR, (cx, cy), radius, width=2)
        requesting = getattr(world, "has_active_request", lambda _id: False)(agent.id)
        if requesting:
            request_ring = radius + max(2, cell_size // 8)
            pg.draw.circle(
                surface,
                HELP_REQUEST_MARKER_COLOR,
                (cx, cy),
                request_ring,
                width=3,
            )
        is_helper = getattr(world, "is_recent_helper", lambda _id: False)(agent.id)
        if is_helper:
            helper_radius = max(3, radius // 2)
            helper_points = [
                (cx, cy - helper_radius),
                (cx + helper_radius, cy),
                (cx, cy + helper_radius),
                (cx - helper_radius, cy),
            ]
            pg.draw.polygon(surface, HELP_GIVER_MARKER_COLOR, helper_points)
# Agent IDs look better without labels cluttering the grid, so we skip rendering text.


def _draw_reactor_meter(surface, world: "World", pg, font) -> None:
    level_ratio = getattr(world, "reactor_level_ratio", lambda: 0.0)()
    level_ratio = max(0.0, min(1.0, level_ratio))
    width, _ = surface.get_size()
    meter_width = min(240, max(140, width // 4))
    meter_height = 14
    padding = 12
    background_rect = pg.Rect(width - meter_width - padding, padding, meter_width, meter_height)
    pg.draw.rect(surface, REACTOR_BAR_BACKGROUND, background_rect, border_radius=6)
    if level_ratio > 0:
        fill_rect = background_rect.copy()
        fill_rect.width = max(2, int(meter_width * level_ratio))
        pg.draw.rect(surface, REACTOR_BAR_FILL, fill_rect, border_radius=6)
    pg.draw.rect(surface, REACTOR_OUTLINE_COLOR, background_rect, width=2, border_radius=6)
    if font:
        label = font.render("Reactor", True, HUD_TEXT_COLOR)
        label_rect = label.get_rect()
        label_rect.midbottom = background_rect.midtop
        label_rect.y -= 4
        surface.blit(label, label_rect)


def draw_hud(surface, lines: Iterable[str], pg, font, padding: int = 8) -> None:
    """
    Draw a simple heads-up display with informational text.
    """
    if font is None:
        return
    y = padding
    for line in lines:
        label = font.render(line, True, HUD_TEXT_COLOR)
        surface.blit(label, (padding, y))
        y += label.get_height() + 4


__all__ = ["require_pygame", "canvas_size", "draw_world", "draw_hud"]
