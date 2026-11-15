"""Choose walking or driving for a request (`profile: "auto"`). Decided with the team 2026-11-15:

1. reach as many destinations as possible;
2. then use the least oxygen per person (the astronaut's o2_g for the requesting user's body mass; the rover's
   o2_g divided by its crew size);
3. then the shorter time; then the order of PROFILES.
A profile that cannot route at all (snap or no-route error) is never chosen, and the reason says why.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from app.core.resources import PROFILES, ProfileId
from app.routing.solver import NoFeasibleRoute

AUTO = "auto"
LABELS = {ProfileId.ASTRONAUT: "walking", ProfileId.CAR: "the vehicle"}


class NoProfileCanRoute(NoFeasibleRoute):
    """No profile can route the request; the message gives each profile's reason (HTTP 422)."""


@dataclass(frozen=True)
class ProfileOutcome:
    profile: ProfileId
    reached: int = 0  # destinations visited
    requested: int = 0  # destinations asked for
    o2_g: float = math.inf  # oxygen per person over the whole route
    time_s: float = math.inf
    error: str | None = None  # set when the profile cannot route at all

    @property
    def feasible(self) -> bool:
        return self.error is None


def choose(outcomes: Sequence[ProfileOutcome]) -> tuple[ProfileOutcome, str]:
    feasible = [o for o in outcomes if o.feasible]
    if not feasible:
        raise NoProfileCanRoute("No mode can route this request: "
                                + "; ".join(f"{LABELS[ProfileId(o.profile)]}: {o.error}" for o in outcomes))
    rank = {p: i for i, p in enumerate(PROFILES)}
    best = min(feasible, key=lambda o: (-o.reached, o.o2_g, o.time_s, rank[ProfileId(o.profile)]))
    return best, explain(best, outcomes)


def explain(best: ProfileOutcome, outcomes: Sequence[ProfileOutcome]) -> str:
    name = LABELS[ProfileId(best.profile)]
    both = "Both modes reach the end" if best.requested == 0 else "Both modes reach the same number of destinations"
    parts = []
    for o in outcomes:
        if o.profile == best.profile:
            continue
        other = LABELS[ProfileId(o.profile)]
        if not o.feasible:
            parts.append(f"{other.capitalize()} cannot do this route ({o.error})")
        elif o.reached < best.reached:
            parts.append(f"{name.capitalize()} reaches {best.reached} of {best.requested} destinations, "
                         f"{other} only {o.reached}")
        elif best.o2_g < o.o2_g:
            parts.append(f"{both}; {name} uses less oxygen per person "
                         f"({best.o2_g:.0f} g vs {o.o2_g:.0f} g)")
        else:
            parts.append(f"{both} with the same oxygen use; {name} takes "
                         f"{best.time_s / 60:.0f} min vs {o.time_s / 60:.0f} min")
    return f"Chose {name}: " + "; ".join(parts) + "."
