from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, layers, route, tiles, users
from app.core.config import Settings
from app.db.session import init_db, make_engine
from app.graph.loader import load_routing_context
from app.layers.base import LayerUnavailable
from app.layers.registry import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if not settings.jwt_secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not set: copy backend/.env.example to backend/.env (see README)")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.layers = build_registry(settings)  # loads every layer once
        engine = make_engine(settings.database_url)
        app.state.session_factory = init_db(engine)
        try:
            app.state.routing = load_routing_context(settings)  # graph + KD-tree, once
        except LayerUnavailable as ex:
            app.state.routing = ex  # /api/route answers 503; layer endpoints keep working
        yield
        engine.dispose()

    app = FastAPI(title="Mars Map API", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(LayerUnavailable)
    async def layer_unavailable(request: Request, exc: LayerUnavailable):
        return JSONResponse(status_code=503, content={"detail": exc.detail, "fix": exc.fix})

    @app.get("/api/hello")
    def hello():
        return {"message": "Hello from FastAPI"}

    app.include_router(layers.router)
    app.include_router(route.router)
    app.include_router(tiles.router)
    app.include_router(auth.router)
    app.include_router(users.router)
    return app


app = create_app()

