from __future__ import annotations

import argparse
import json
from typing import Dict

from agent_town_sim import DEBUG_MODE, World, seed_world
from agent_town_sim.map import canvas_size, draw_hud, draw_world, require_pygame


def summarize_world(world: World) -> Dict[str, object]:
    summary = {
        "tick": world.tick,
        "size": {"width": world.width, "height": world.height},
        "agents": {
            agent.id: {"name": agent.name, "position": agent.position, "energy": agent.energy}
            for agent in world.agents.values()
        },
    }
    if hasattr(world, "active_help_requests"):
        requests = world.active_help_requests()
        if requests:
            summary["help_requests"] = {
                agent_id: {"position": position, "amount": amount}
                for agent_id, (position, amount) in requests.items()
            }
    return summary


def interactive_simulation(
    agent_count: int,
    debug: bool,
    cell_size: int = 48,
    fps: int = 60,
    steps_per_second: float = 2.0,
    w: int = 32,
    h: int = 32
) -> World:
    pg = require_pygame()
    world = seed_world(agent_count=agent_count, debug=debug, width=w, height=h)
    pg.init()
    width, height = canvas_size(world, cell_size)
    screen = pg.display.set_mode((width, height))
    pg.display.set_caption("Agent Town Grid")
    clock = pg.time.Clock()
    agent_font = pg.font.SysFont(None, max(16, int(cell_size * 0.45)))
    hud_font = pg.font.SysFont(None, 20)

    paused = False
    running = True
    step_interval = 1.0 / max(steps_per_second, 0.0001)
    accumulator = 0.0

    print("Controls: ESC to quit | SPACE to pause/resume | N to step once while paused")

    while running:
        dt = clock.tick(fps) / 1000.0
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    running = False
                elif event.key == pg.K_SPACE:
                    paused = not paused
                elif event.key == pg.K_n:
                    world.step()

        if not paused:
            accumulator += dt
            while accumulator >= step_interval:
                world.step()
                accumulator -= step_interval

        draw_world(screen, world, cell_size, font=agent_font)
        carried_energy = sum(agent.energy for agent in world.agents.values())
        hud_lines = [
            f"Tick: {world.tick}",
            "Paused" if paused else f"Steps/sec: {steps_per_second:.2f}",
            f"Agents: {len(world.agents)}",
            f"Carried energy: {carried_energy}",
        ]
        if hasattr(world, "reactor"):
            hud_lines.append(f"Reactor: {world.reactor.energy}/{world.reactor.capacity}")
        if hasattr(world, "deposit_history"):
            history = world.deposit_history()
            recent_reports = history[-3:]
            for tick, agent_id, actual, claimed, lie in reversed(recent_reports):
                marker = "✔" if not lie else "✘"
                hud_lines.append(
                    f"{agent_id} dep:{actual} rep:{claimed} lie:{marker} (t{tick})"
                )
        draw_hud(screen, hud_lines, pg, hud_font)
        pg.display.flip()

    pg.quit()
    return world


def run_simulation(agent_count: int, ticks: int, debug: bool) -> World:
    world = seed_world(agent_count=agent_count, debug=debug)
    for _ in range(ticks):
        world.step()
    print(json.dumps(summarize_world(world), indent=2))
    return world


def main() -> None:
    parser = argparse.ArgumentParser(description="Bare bones Agent Town simulator.")
    parser.add_argument("--agents", type=int, default=4, help="Agents to seed into the world.")
    parser.add_argument("--ticks", type=int, default=20, help="Ticks to run in non-interactive mode.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run in interactive mode with a pygame window.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=DEBUG_MODE,
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=30,
        help="Pixel size of each grid cell in interactive mode.",
    )
    parser.add_argument(
        "--steps-per-second",
        type=float,
        default=2.0,
        help="Simulation speed when running interactive mode.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=60,
        help="Target frame rate for interactive mode.",
    )

    parser.add_argument(
        "--w",
        type=int,
        default=60
    )

    parser.add_argument(
        "--h",
        type=int,
        default=32
    )

    args = parser.parse_args()

    if args.interactive:
        try:
            interactive_simulation(
                agent_count=max(0, args.agents),
                debug=args.debug,
                cell_size=max(8, args.cell_size),
                fps=max(1, args.fps),
                steps_per_second=max(0.1, args.steps_per_second),
                w=args.w,
                h=args.h
            )
        except RuntimeError as exc:
            print(exc)
    else:
        run_simulation(agent_count=max(0, args.agents), ticks=max(0, args.ticks), debug=args.debug)


if __name__ == "__main__":
    main()
