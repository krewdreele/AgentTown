from __future__ import annotations

import os


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG_MODE = _env_flag("AGENT_TOWN_DEBUG", False)


__all__ = ["DEBUG_MODE"]
