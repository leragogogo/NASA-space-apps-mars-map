"""POST /api/route: multi-destination route for a profile (thin wrapper around app.routing.request).

Login required: the token identifies the user, the user's row is loaded from the database, and its body mass
is used for the oxygen, CO2 and water estimates (never for the route itself)."""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.layers.base import LayerUnavailable
from app.routing.request import RouteRequestError, handle_route_request
from app.routing.snap import SnapError
from app.routing.solver import NoFeasibleRoute
from app.schemas.route import RouteRequest, RouteResponse

router = APIRouter(prefix="/api", tags=["route"])


@router.post("/route", response_model=RouteResponse, response_model_by_alias=True,
             summary="Route over several destinations")
def post_route(req: RouteRequest, request: Request, user: User = Depends(get_current_user)):
    ctx = request.app.state.routing
    if isinstance(ctx, LayerUnavailable):
        raise ctx  # -> HTTP 503 with detail and fix
    try:
        weather = request.app.state.layers.get("weather") if req.season else None
    except LayerUnavailable:
        weather = None  # route still works; a warning says the weather is unknown
    try:
        return handle_route_request(ctx, req, request.app.state.settings, weather, user.body_mass_kg)
    except (SnapError, RouteRequestError, NoFeasibleRoute) as ex:
        raise HTTPException(422, str(ex))
