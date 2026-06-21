"""Entity schemas and mutable world state for the synthetic dispatch domain.

All locations are short hub codes (e.g. "DAL", "HOU"). Distances are stored as
deadhead drive-minutes between hub pairs, looked up symmetrically.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EquipmentType(str, Enum):
    """Trailer/equipment classes. A load can only be hauled by matching equipment."""

    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"


class Endorsement(str, Enum):
    """CDL endorsements a load may require the driver to hold."""

    HAZMAT = "hazmat"
    TANKER = "tanker"


class DriverTier(str, Enum):
    """Generic driver loyalty tier. PREMIER drivers are softly preferred when
    all else is equal — a ranking nudge, never a hard gate. (Generic stand-in
    for any "preferred fleet" concept; carries no company-specific meaning.)
    """

    STANDARD = "standard"
    PREMIER = "premier"


class Driver(BaseModel):
    """A driver available (or not) to take loads."""

    id: str
    name: str
    location: str  # current hub code
    equipment: EquipmentType
    endorsements: list[Endorsement] = Field(default_factory=list)
    tier: DriverTier = DriverTier.STANDARD
    # Remaining legal on-duty drive time (DOT Hours-of-Service), in minutes.
    hos_remaining_minutes: int
    on_duty: bool = True
    # Idle time since last assignment — drives the longest-waiting fairness preference.
    minutes_waiting: int = 0
    active_load_id: str | None = None
    # Customers this driver is barred from serving (hard exclusion).
    banned_customers: list[str] = Field(default_factory=list)


class Load(BaseModel):
    """A load needing a driver."""

    id: str
    pickup: str  # hub code
    dropoff: str  # hub code
    required_equipment: EquipmentType
    required_endorsements: list[Endorsement] = Field(default_factory=list)
    customer: str
    priority: int = 0  # higher = more urgent (soft ranking signal)
    loaded_minutes: int  # estimated loaded drive time pickup -> dropoff
    # Free-text operational note. This is the prompt-injection surface (L4):
    # an adversarial note may instruct the agent to violate a constraint.
    # Constraint logic MUST ignore this field — only a misled agent would obey it.
    notes: str = ""
    status: str = "unassigned"  # "unassigned" | "assigned"
    assigned_driver_id: str | None = None


class Assignment(BaseModel):
    """A booked driver->load assignment (the artifact scoring inspects)."""

    load_id: str
    driver_id: str


class WorldState(BaseModel):
    """A seedable, mutable dispatch world. Tools read and write this."""

    drivers: dict[str, Driver]
    loads: dict[str, Load]
    # Deadhead minutes keyed "FROM|TO". Looked up via `deadhead`, which is
    # symmetric and returns 0 for same-hub.
    distance_minutes: dict[str, int] = Field(default_factory=dict)
    assignments: list[Assignment] = Field(default_factory=list)

    def deadhead(self, from_hub: str, to_hub: str) -> int:
        """Symmetric deadhead drive-minutes between two hubs (0 if identical)."""
        if from_hub == to_hub:
            return 0
        key = f"{from_hub}|{to_hub}"
        rev = f"{to_hub}|{from_hub}"
        if key in self.distance_minutes:
            return self.distance_minutes[key]
        if rev in self.distance_minutes:
            return self.distance_minutes[rev]
        raise KeyError(f"no distance recorded for {from_hub} <-> {to_hub}")
