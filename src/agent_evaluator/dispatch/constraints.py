"""Hard constraints and soft preferences for the synthetic dispatch domain.

HARD constraints, if violated by a booked assignment, make it *wrong* — the
scorer (a later phase) flags these by inspecting final world state. SOFT
preferences only rank otherwise-legal candidates; violating one is suboptimal,
not invalid.

These are deliberately generic freight-dispatch rules. No business-specific
priority ordering, driver tiers, or tuned constants are encoded here.
"""

from __future__ import annotations

from agent_evaluator.dispatch.models import Driver, DriverTier, Load, WorldState

# (name, description) — documentation + lets the scorer enumerate dimensions.
HARD_CONSTRAINTS: list[tuple[str, str]] = [
    ("equipment_match", "Driver's equipment must match the load's required equipment."),
    ("endorsements", "Driver must hold every endorsement the load requires."),
    ("hours_of_service", "Deadhead + loaded drive time must fit remaining HOS minutes."),
    ("availability", "Driver must be on duty and not already on another active load."),
    ("customer_ban", "Driver must not be banned from the load's customer."),
]

SOFT_PREFERENCES: list[tuple[str, str]] = [
    ("deadhead", "Prefer the driver with the shortest empty miles to pickup."),
    ("priority", "Prefer covering higher-priority loads first."),
    ("fairness", "Prefer the longest-waiting idle driver."),
    ("tier", "Prefer PREMIER-tier drivers when otherwise equal."),
]


def hard_violations(driver: Driver, load: Load, world: WorldState) -> list[str]:
    """Return the names of every HARD constraint this pairing violates.

    Empty list == a legal assignment. The driver's `active_load_id` is allowed
    to equal this load (re-checking an already-booked pairing is not a
    self-conflict).
    """
    violations: list[str] = []

    if driver.equipment != load.required_equipment:
        violations.append("equipment_match")

    if any(e not in driver.endorsements for e in load.required_endorsements):
        violations.append("endorsements")

    total_drive = world.deadhead(driver.location, load.pickup) + load.loaded_minutes
    if total_drive > driver.hos_remaining_minutes:
        violations.append("hours_of_service")

    busy = driver.active_load_id is not None and driver.active_load_id != load.id
    if not driver.on_duty or busy:
        violations.append("availability")

    if load.customer in driver.banned_customers:
        violations.append("customer_ban")

    return violations


def is_eligible(driver: Driver, load: Load, world: WorldState) -> bool:
    """True iff the driver can legally take the load (no hard violations)."""
    return not hard_violations(driver, load, world)


def soft_signals(driver: Driver, load: Load, world: WorldState) -> dict[str, int]:
    """Raw soft-preference signals for ranking eligible candidates.

    Lower `deadhead_minutes` is better; higher `priority` and `minutes_waiting`
    are better. No blended score is computed here — ranking policy belongs to
    whoever consumes these (kept explicit and transparent, unlike a tuned
    proprietary comparator).
    """
    return {
        "deadhead_minutes": world.deadhead(driver.location, load.pickup),
        "priority": load.priority,
        "minutes_waiting": driver.minutes_waiting,
        "premier": 1 if driver.tier == DriverTier.PREMIER else 0,
    }
