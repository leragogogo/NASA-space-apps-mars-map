"""Step 1: which directed edges exist. Pure topology, no data besides the valid mask.

Edges connect each valid cell to its valid neighbours (8-neighbourhood by default). Every
neighbour pair appears in both directions, because uphill and downhill cost differently.
Nodata cells have no edges (they stay in the graph as isolated nodes so that
node id = row * ncols + col holds).
"""
from __future__ import annotations

import numpy as np

from app.layers.contracts import GridSpec

# (d_row, d_col); row 0 is the north row.
_OFFSETS_4 = ((-1, 0), (0, -1), (0, 1), (1, 0))
_OFFSETS_8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
_OFFSETS = {4: _OFFSETS_4, 8: _OFFSETS_8}


def enumerate_edges(grid: GridSpec, valid: np.ndarray, neighbours: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Return (src, dst): int32 node ids of every directed edge, sorted by (src, dst).

    The position of an edge in these arrays is its edge id, used by every edge attribute array.
    """
    if neighbours not in _OFFSETS:
        raise ValueError(f"neighbours must be 4 or 8, got {neighbours}")
    valid = np.asarray(valid, dtype=bool)
    if valid.shape != grid.shape:
        raise ValueError(f"valid shape {valid.shape} != grid shape {grid.shape}")
    nrows, ncols = grid.shape
    rows, cols = np.indices(grid.shape)
    node = rows * ncols + cols
    src_parts, dst_parts = [], []
    for d_row, d_col in _OFFSETS[neighbours]:
        r2, c2 = rows + d_row, cols + d_col
        inside = (r2 >= 0) & (r2 < nrows) & (c2 >= 0) & (c2 < ncols)
        ok = np.zeros(grid.shape, dtype=bool)
        ok[inside] = valid[inside] & valid[r2[inside], c2[inside]]
        src_parts.append(node[ok])
        dst_parts.append((r2 * ncols + c2)[ok])
    src = np.concatenate(src_parts).astype(np.int32)
    dst = np.concatenate(dst_parts).astype(np.int32)
    order = np.lexsort((dst, src))
    return src[order], dst[order]
