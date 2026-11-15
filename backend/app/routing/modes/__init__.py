"""Walking or driving: the `profile: "auto"` rule of POST /api/route."""
from app.routing.modes.select import AUTO, LABELS, NoProfileCanRoute, ProfileOutcome, choose, explain

__all__ = ["AUTO", "LABELS", "NoProfileCanRoute", "ProfileOutcome", "choose", "explain"]
