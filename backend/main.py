from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import layers, tiles
from app.core.config import Settings
from app.layers.base import LayerUnavailable
from app.layers.registry import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.layers = build_registry(settings)  # loads every layer once
        yield

    app = FastAPI(title="Mars Map API", lifespan=lifespan)
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
    app.include_router(tiles.router)
    return app


app = create_app()
