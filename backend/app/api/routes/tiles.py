"""/api/tiles/{source}/{z}/{row}/{col}: map tiles straight from data/raw/tiles (no upstream calls)."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api", tags=["tiles"])


@router.get("/tiles/{source}/{z}/{row}/{col}", response_class=FileResponse, summary="One map tile")
def get_tile(request: Request, source: str, z: int, row: int, col: int):
    hit = request.app.state.layers.tiles.path(source, z, row, col)
    if hit is None:
        raise HTTPException(404, "Tile not available")
    path, media_type = hit
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
