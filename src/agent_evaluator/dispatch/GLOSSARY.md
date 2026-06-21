# Dispatch domain — terminology & scrubbing audit

This synthetic dispatch domain is deliberately generic and publishable. It was
abstracted from a real freight-dispatch system; **all company-specific
vocabulary and tuned business logic were stripped or renamed** before any of it
landed in this package.

`tests/test_dispatch_scrub.py` enforces that none of the original terms reappear
in the package source or in the serialized scenario data. This file is the audit
trail — it is the *only* place the original terms are named, so the guard does
not scan it.

## Invented generic terms (original → published)

| Original (proprietary) | Published (generic) | Notes |
|---|---|---|
| "5F" / "FleetForce" preferred driver class | **`DriverTier.PREMIER`** (vs `STANDARD`) | A soft loyalty-tier tiebreak only — never a hard gate. |
| "preload" (pre-staging a driver's next load) | **"prebook"** | A normal forward assignment of a driver's next load. |
| frac / mine / PO / sand / well-diversion | dropped | Replaced by generic pickup/dropoff hubs and `customer`. |
| subcontractor earnings targets / allocation | dropped | No allocation/earnings policy is modeled. |
| HSE / safety-score gating | dropped | No safety-score gating is modeled. |
| "up for grabs" vendor-exclusivity | dropped | Single-assignment model; no multi-vendor exclusivity. |
| the tuned ~20-criterion priority comparator | dropped | Soft signals are raw, transparent numbers; no blended/tuned ranking. |
| data-tuned magic constants (5 min / 6 h / p99 / 90th pct …) | dropped | Hub distances and HOS values are round, invented numbers. |

## What was kept (industry-standard, not proprietary)

Hours-of-Service, equipment-type matching, CDL endorsements (hazmat), driver
availability, customer bans (hard constraints); deadhead distance, load
priority, longest-waiting fairness, premier-tier (soft preferences). "Deadhead"
and "linehaul" are standard trucking terms, not company vocabulary.
