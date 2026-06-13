"""Scenario registry — auto-discovers and loads all scenario definitions."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable

from agent_evaluator.models import Scenario

# Registry of scenario builder functions
_REGISTRY: dict[str, Callable[[], Scenario]] = {}


def register(scenario_id: str):
    """Decorator to register a scenario builder function."""
    def wrapper(fn: Callable[[], Scenario]) -> Callable[[], Scenario]:
        _REGISTRY[scenario_id] = fn
        return fn
    return wrapper


def load_all_scenarios() -> dict[str, Scenario]:
    """Import all scenario modules and collect registered scenarios."""
    # Force import of all scenario modules to trigger @register decorators
    import scenarios
    for _, name, _ in pkgutil.iter_modules(scenarios.__path__):
        if name != "registry":
            importlib.import_module(f"scenarios.{name}")

    return {sid: builder() for sid, builder in _REGISTRY.items()}


def load_scenario(scenario_id: str) -> Scenario:
    """Load a single scenario by ID."""
    all_scenarios = load_all_scenarios()
    if scenario_id not in all_scenarios:
        available = ", ".join(sorted(all_scenarios.keys()))
        raise ValueError(
            f"Unknown scenario '{scenario_id}'. Available: {available}"
        )
    return all_scenarios[scenario_id]
