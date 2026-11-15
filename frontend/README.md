# Mars Map frontend

"Google Maps for Mars": a Leaflet map of the East Melas / Coprates Chasma demo area (Valles Marineris) with four layers:
base imagery, relief and walkability, points of interest, and seasonal dust-storm risk. Click anywhere to see what's
there: elevation, slope, whether it's passable on foot or by rover, the areas the point lies in and the dust-storm
risk for the selected season when those layers are on. Routing comes later (`src/features/route/`).

All data comes from our FastAPI backend (`/api/get-layer-*`, `/api/tiles/...`); the app never calls NASA servers.

## Run

Start the backend first (see the root `README.md`: data download, `backend/.env`, uvicorn on :8000). Then:

```bash
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api/*` to `http://localhost:8000`; set `MARS_API_URL` to use another
backend, e.g. `MARS_API_URL=http://localhost:8001 npm run dev`.

## Test and lint

```bash
npm test
npm run lint
```

Tests run in jsdom with `react-leaflet` replaced by `src/test/reactLeafletMock.jsx` (see `vite.config.js`), because Leaflet
cannot draw vector layers without a real browser. The mock freezes construction-only props the way real Leaflet does,
so remount `key`s are tested. Check map rendering itself in the browser.

## Layout

```
src/api/marsApi.js          the only module that calls the backend (ApiError with the backend's `fix` command on 503)
src/hooks/useLayer.js       load-on-demand layer data: { status, data, error }
src/config/                 AOI, zoom limits, POI categories, seasons, panes, default view
src/features/map/           MapContainer (EPSG4326), cursor coordinates
src/features/layers/        TrekTileLayer, ReliefLayer, PoiLayer, WeatherLayer (+ pure helpers)
src/components/             LayerPanel, Legend, PointInfo
src/utils/                  escapeHtml (popups), point-in-polygon
```

## Notes

- The map uses `L.CRS.EPSG4326`: Mars Trek tiles are plain lat/lon, not Web Mercator.
- All Trek tiles are displayed at 256 px, even the 512 px HiRISE / CTX-global images.
- Vector and overlay layers live in fixed Leaflet panes (`PANES` in `src/config/layers.js`), so their stacking order
  does not depend on the order they were switched on.
- POI areas and the dust-storm grid are click-through; a map click opens the point card, which lists the areas and the
  dust-storm message for that spot. POI dots keep their own popups.
- Slope and elevation values are approximate (200 m grid); dust-storm messages are shown verbatim from the backend.
