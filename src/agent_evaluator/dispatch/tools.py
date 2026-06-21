"""The dispatch tool interface an agent calls.

Read-only lookups + the single state-mutating write (`assign_driver_to_load`).
Every method returns a plain JSON-serializable dict (tool-result shaped). On
failure a method returns ``{"error": "..."}`` rather than raising, so the agent
observes the failure and can recover (exercises error-recovery scoring).

The write is PERMISSIVE: it enforces only the double-assignment race guard
(mirroring the real system's atomic conditional UPDATE). It does NOT check
hard constraints — a misled or careless agent can book an illegal assignment,
and the scorer catches it later by inspecting world state. That is the point.

Optional `fault` injects a transient failure (L3): the `on_call`-th call to the
named tool returns an error instead of its normal result, so the agent must
recover. The call is still recorded in `calls` before the error is returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_evaluator.dispatch.models import Assignment, WorldState

if TYPE_CHECKING:
    from agent_evaluator.dispatch.scenario import ToolFault


class DispatchTools:
    """Wraps a WorldState and exposes the agent-facing dispatch tools."""

    def __init__(self, world: WorldState, fault: ToolFault | None = None):
        self.world = world
        # Ordered record of every tool call, for trajectory inspection/scoring.
        self.calls: list[tuple[str, dict]] = []
        self._fault = fault
        self._fault_seen = 0

    def _record(self, name: str, args: dict) -> dict | None:
        """Record a call; return an error dict if this call is the injected fault."""
        self.calls.append((name, args))
        if self._fault is not None and self._fault.tool == name:
            self._fault_seen += 1
            if self._fault_seen == self._fault.on_call:
                return {"error": self._fault.error}
        return None

    # ── read-only lookups ────────────────────────────────────────────────

    def list_available_drivers(self) -> dict:
        """List on-duty, unassigned drivers as minimal stubs: ``{id, location}``.

        Full attributes (equipment, endorsements, tier, HOS, customer bans) are
        deliberately omitted — the agent must call `get_driver`,
        `get_hours_of_service`, and `get_distance` to gather what it needs to
        judge eligibility. This forces genuine multi-step tool use (so "did you
        verify before assigning?" becomes a scorable behavior) and mirrors a
        real dispatch system where driver data is spread across services.
        """
        if (fault := self._record("list_available_drivers", {})) is not None:
            return fault
        stubs = [
            {"id": d.id, "location": d.location}
            for d in self.world.drivers.values()
            if d.on_duty and d.active_load_id is None
        ]
        return {"drivers": stubs}

    def get_driver(self, driver_id: str) -> dict:
        if (fault := self._record("get_driver", {"driver_id": driver_id})) is not None:
            return fault
        driver = self.world.drivers.get(driver_id)
        if driver is None:
            return {"error": f"no driver with id {driver_id!r}"}
        return driver.model_dump()

    def get_load(self, load_id: str) -> dict:
        if (fault := self._record("get_load", {"load_id": load_id})) is not None:
            return fault
        load = self.world.loads.get(load_id)
        if load is None:
            return {"error": f"no load with id {load_id!r}"}
        return load.model_dump()

    def get_hours_of_service(self, driver_id: str) -> dict:
        if (fault := self._record("get_hours_of_service", {"driver_id": driver_id})) is not None:
            return fault
        driver = self.world.drivers.get(driver_id)
        if driver is None:
            return {"error": f"no driver with id {driver_id!r}"}
        return {"driver_id": driver_id, "hos_remaining_minutes": driver.hos_remaining_minutes}

    def get_distance(self, from_location: str, to_location: str) -> dict:
        args = {"from_location": from_location, "to_location": to_location}
        if (fault := self._record("get_distance", args)) is not None:
            return fault
        try:
            minutes = self.world.deadhead(from_location, to_location)
        except KeyError as e:
            return {"error": str(e)}
        return {**args, "deadhead_minutes": minutes}

    # ── the write ────────────────────────────────────────────────────────

    def assign_driver_to_load(self, driver_id: str, load_id: str) -> dict:
        """Book a driver onto a load.

        Permissive: only the double-assignment guard and existence checks
        apply. Hard-constraint legality is intentionally NOT enforced here.
        """
        args = {"driver_id": driver_id, "load_id": load_id}
        if (fault := self._record("assign_driver_to_load", args)) is not None:
            return fault
        driver = self.world.drivers.get(driver_id)
        load = self.world.loads.get(load_id)
        if driver is None:
            return {"error": f"no driver with id {driver_id!r}"}
        if load is None:
            return {"error": f"no load with id {load_id!r}"}
        # Race guard, mirroring the real "WHERE status='unassigned'" atomic update.
        if load.status != "unassigned":
            return {
                "error": f"load {load_id!r} already {load.status}"
                f" (driver {load.assigned_driver_id!r})"
            }

        load.status = "assigned"
        load.assigned_driver_id = driver_id
        driver.active_load_id = load_id
        self.world.assignments.append(Assignment(load_id=load_id, driver_id=driver_id))
        return {"status": "assigned", "load_id": load_id, "driver_id": driver_id}
