"""Seedable construction of a synthetic dispatch world.

`build_world(seed)` returns a deterministic WorldState — same seed, identical
world — so scenarios are reproducible. Hubs and the deadhead matrix are fixed;
the seed varies which drivers/loads populate the world. Scenarios that need an
exact hand-crafted situation should construct WorldState directly instead.
"""

from __future__ import annotations

import random

from agent_evaluator.dispatch.models import (
    Driver,
    Endorsement,
    EquipmentType,
    Load,
    WorldState,
)

# Fixed hub set and a symmetric deadhead matrix (drive-minutes). Generic hub
# codes — no real-world or business-specific geography.
HUBS: list[str] = ["DAL", "HOU", "AUS", "SAT", "OKC"]

_DISTANCE_MINUTES: dict[str, int] = {
    "DAL|HOU": 230,
    "DAL|AUS": 195,
    "DAL|SAT": 275,
    "DAL|OKC": 200,
    "HOU|AUS": 165,
    "HOU|SAT": 200,
    "HOU|OKC": 430,
    "AUS|SAT": 80,
    "AUS|OKC": 380,
    "SAT|OKC": 460,
}

_EQUIPMENT = list(EquipmentType)
_CUSTOMERS = ["acme", "globex", "initech", "umbrella"]


def build_world(seed: int = 0, *, num_drivers: int = 5, num_loads: int = 3) -> WorldState:
    """Build a deterministic world from `seed`.

    Drivers get varied hubs, equipment, HOS, and wait times; loads get varied
    pickup/dropoff, required equipment, priority, and drive times. Roughly a
    third of loads require an endorsement, so endorsement coverage is exercised.
    """
    rng = random.Random(seed)

    drivers: dict[str, Driver] = {}
    for i in range(num_drivers):
        did = f"D{i + 1}"
        endorsements = [Endorsement.HAZMAT] if rng.random() < 0.4 else []
        drivers[did] = Driver(
            id=did,
            name=f"Driver {i + 1}",
            location=rng.choice(HUBS),
            equipment=rng.choice(_EQUIPMENT),
            endorsements=endorsements,
            hos_remaining_minutes=rng.choice([240, 360, 480, 600]),
            on_duty=rng.random() < 0.85,
            minutes_waiting=rng.choice([0, 30, 90, 180, 300]),
        )

    loads: dict[str, Load] = {}
    for i in range(num_loads):
        lid = f"L{i + 1}"
        pickup, dropoff = rng.sample(HUBS, 2)
        required_endorsements = [Endorsement.HAZMAT] if rng.random() < 0.33 else []
        loads[lid] = Load(
            id=lid,
            pickup=pickup,
            dropoff=dropoff,
            required_equipment=rng.choice(_EQUIPMENT),
            required_endorsements=required_endorsements,
            customer=rng.choice(_CUSTOMERS),
            priority=rng.choice([0, 1, 2]),
            loaded_minutes=_symmetric_minutes(pickup, dropoff),
        )

    return WorldState(
        drivers=drivers,
        loads=loads,
        distance_minutes=dict(_DISTANCE_MINUTES),
    )


def _symmetric_minutes(a: str, b: str) -> int:
    if a == b:
        return 0
    return _DISTANCE_MINUTES.get(f"{a}|{b}") or _DISTANCE_MINUTES[f"{b}|{a}"]
