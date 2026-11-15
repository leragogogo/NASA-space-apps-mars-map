# Mars Map Website (Base Map + Layers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Google Maps for Mars" web app with a full-screen Leaflet map of the East Melas / Coprates Chasma demo area. Users can switch base imagery, toggle the relief, points-of-interest and dust-storm layers, and click anywhere to see elevation and slope. There is no routing yet.

**Architecture:** A standalone React + Vite single-page app in `/Users/sielprar/PycharmProjects/Nasa web`. It talks only to the team's existing FastAPI layer backend (`/api/get-layer-one … four`, `/api/tiles/...`, `/api/get-layer-two/point`) through the Vite dev proxy, and never to NASA servers directly. The map uses `L.CRS.EPSG4326` because Mars Trek tiles are plain lat/lon, not Web Mercator. Each layer is a small React component built on react-leaflet primitives. All UI state sits in one flat `view` object in `App`.

**Tech Stack:** React 19, Vite 8, Leaflet 1.9 + react-leaflet 5, Vitest + React Testing Library + jsdom. The backend is Python FastAPI from the team repo; it is reused, not modified.

---

## Context the engineer needs

### Where things are
- **Team repo (data + backend):** `/Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map`
  - Project rules and domain context: `AGENTS.md`, `context/skills/mars-mvp-data/SKILL.md` (sections 2, 6, 8).
  - Data is already downloaded: `data/raw/` (tiles, DEM, POI GeoJSON) and `data/derived/weather/`.
  - **The layer endpoints only exist on the remote branch `origin/feature/layer-ingestion` (commit `f76d7c5`).** The local checkout is on a different commit without them. Task 0 checks that branch out into a separate worktree, so the user's checkout is never touched.
- **This website:** `/Users/sielprar/PycharmProjects/Nasa web` (empty except `.claude/`, and not yet a git repo).

### Backend API (verified against real data on 2026-11-15)
| Endpoint | Returns |
|---|---|
| `GET /api/get-layer-one` | `{layer, default_source: "ctx_coprates", sources: [TileSource…]}`. Sources: `ctx_coprates`, `ctx_global`, `hirise` |
| `GET /api/get-layer-two` | `{layer, bounds, resolution_m, elevation_range_m, slope_classes[5], overlay: {url, bounds}, hillshade_sources: [TileSource…], caveats[]}`. Hillshade: `hillshade_color`, `hillshade_ctx` |
| `GET /api/get-layer-two/walkability.png` | PNG of slope classes covering the AOI (use as `ImageOverlay`) |
| `GET /api/get-layer-two/point?lon=&lat=` | `{lon, lat, elevation_m, slope_deg, slope_class, walkable, vehicle, approximate}`; **404** outside the AOI with `detail` string |
| `GET /api/get-layer-three` | GeoJSON FeatureCollection plus `categories: {id: count}`, `overlays: [TileSource crism_sulfate]`. Feature properties: `id, category, name, description, source, raw`. Longitudes are already −180..180 |
| `GET /api/get-layer-four?season=autumn\|winter\|spring\|summer` | GeoJSON of 1600 1° cells (lon −90..−50, lat −30..10) plus `season_name, caveat, legend: {Low, Moderate, High → hex}, aoi_summary`. Cell properties include `display_risk` (may be `null`), `display_style` (`solid\|hatched\|grey`), `confidence`, `message` |
| `GET /api/tiles/{source}/{z}/{y}/{x}` | Tile image; 404 if missing |
| any layer whose data is missing | **503** `{detail, fix}`, where `fix` is the shell command to run |

`TileSource` = `{id, title, tile_url: "/api/tiles/<id>/{z}/{y}/{x}", format, tile_size, min_zoom, max_zoom, bounds: [[s,w],[n,e]], coverage_note}`.

AOI (demo area): west −71.8, south −13.4, east −68.0, north −10.0.

### Domain gotchas (read before coding)
1. **CRS:** use `L.CRS.EPSG4326`. At zoom `z` Trek has `2^(z+1)` columns × `2^z` rows, which matches Leaflet's EPSG4326 `{z}/{y}/{x}` exactly. Tiles exist for zooms 5–9 only, so set `minNativeZoom`/`maxNativeZoom` and let Leaflet scale them.
2. **Tile size:** `ctx_global` and `hirise` are 512 px images, but each one covers the same geographic cell as a 256 px tile. **Always pass `tileSize={256}`.** With `512`, Leaflet would place them at the wrong position.
3. **react-leaflet `GeoJSON` ignores `data` changes after mount.** Give it a `key` that changes with the data (season, or the category list).
4. **Data-sufficiency rule (mandatory, SKILL.md §2/§6):** render the weather `message` verbatim, style cells by confidence (solid, hatched, or grey), show the global caveat, and label slope and elevation values as approximate.
5. **No Leaflet scale bar:** Leaflet's scale control assumes Earth's radius, so leave it out.
6. **Leaflet in jsdom cannot draw vector layers** (no SVG renderer). Tests therefore alias `react-leaflet` to a small mock (Task 1), and the real map is checked in the browser (Task 13).

### Decisions taken (no input needed)
- **React + react-leaflet** rather than plain Leaflet, because it matches the team repo's `frontend/` stack and lets this code be merged there later.
- **This app talks only to the existing backend.** It does not read files from `data/` itself, which follows the project rule "the frontend consumes only our FastAPI backend".
- **Folder layout follows the team rule** `src/<area>/<Module>/` with tests next to the source as `<Name>.test.jsx`.

### Out of scope (YAGNI)
Routing, the route UI, search, a custom Mars scale bar, layer opacity sliders, and deployment.

---

## File structure

```
Nasa web/
  package.json                     scripts + deps
  vite.config.js                   React plugin, /api proxy, Vitest config (jsdom, react-leaflet mock alias)
  index.html                       page shell
  .gitignore
  README.md                        how to run backend + frontend + tests
  scripts/dev-backend.sh           starts the team backend from the worktree on :8000
  .claude/launch.json              preview config for the dev server
  src/
    main.jsx                       React entry, imports leaflet CSS
    App.jsx / App.css / index.css  app shell: wires state, data, map, panels; layout styles
    App.test.jsx                   integration test (mocked fetch + mocked react-leaflet)
    test/setup.js                  jest-dom matchers + cleanup
    test/reactLeafletMock.jsx      test double for react-leaflet (aliased in vite.config.js)
    test/fixtures.js               API response fixtures + fetch helpers
    config/map.js (+test)          AOI, centre, zoom limits, max bounds, transparent tile, formatLatLng
    config/layers.js               DEFAULT_VIEW, SEASONS, POI_CATEGORIES, opacities, sulfate id
    utils/html.js (+test)          escapeHtml for Leaflet popup HTML
    api/marsApi.js (+test)         fetch wrapper + one function per endpoint, ApiError
    hooks/useLayer.js (+test)      load-on-demand hook with loading/error/stale handling
    features/map/MarsMap/                 MapContainer (EPSG4326), zoom control, click events
    features/map/CoordinateReadout/       live cursor lat/lon
    features/layers/TrekTileLayer/        TileLayer with Trek defaults (used by base, hillshade, sulfate)
    features/layers/ReliefLayer/          hillshade tiles + walkability ImageOverlay
    features/layers/PoiLayer/             POI GeoJSON + CRISM sulfate tiles; poiHelpers.js
    features/layers/WeatherLayer/         dust-storm GeoJSON; weatherHelpers.js; HatchPatterns.jsx
    components/LayerPanel/                left panel: base map, relief, POI, dust-storm controls
    components/Legend/                    legend for active layers incl. caveats and verbatim messages
    components/PointInfo/                 "what's here" card after a map click
```

---

### Task 0: Run the team's layer backend

**Files:**
- Create: `/Users/sielprar/PycharmProjects/Nasa web/scripts/dev-backend.sh`

- [ ] **Step 1: Create a worktree of the backend branch (does not touch the user's checkout)**

```bash
cd /Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map
git fetch origin
git worktree add --detach ../mars-backend origin/feature/layer-ingestion
```

Expected: `HEAD is now at f76d7c5 layer ingestion first iteration` (or a newer commit if the team pushed one).

- [ ] **Step 2: Write the start script**

`/Users/sielprar/PycharmProjects/Nasa web/scripts/dev-backend.sh`:

```bash
#!/usr/bin/env bash
# Starts the team's FastAPI layer backend on :8000 for local development.
# Code comes from the worktree of origin/feature/layer-ingestion; data and the Python venv come from the main checkout.
set -euo pipefail

TEAM_REPO="${TEAM_REPO:-/Users/sielprar/PycharmProjects/NASA/NASA-space-apps-mars-map}"
BACKEND_DIR="${BACKEND_DIR:-/Users/sielprar/PycharmProjects/NASA/mars-backend/backend}"

export MARS_DATA_DIR="${MARS_DATA_DIR:-$TEAM_REPO/data}"
cd "$BACKEND_DIR"
exec "$TEAM_REPO/backend/.venv/bin/uvicorn" main:app --port 8000 "$@"
```

```bash
chmod +x "/Users/sielprar/PycharmProjects/Nasa web/scripts/dev-backend.sh"
```

- [ ] **Step 3: Start it in the background and check the endpoints**

```bash
"/Users/sielprar/PycharmProjects/Nasa web/scripts/dev-backend.sh"
```

(Run it in the background or in a separate terminal.) Then:

```bash
curl -s localhost:8000/api/get-layer-one | head -c 200
```

Expected: JSON starting with `{"layer":"base_imagery","default_source":"ctx_coprates",...`.

```bash
curl -s "localhost:8000/api/get-layer-two/point?lon=-70&lat=-12"
```

Expected: `{"lon":-70.0,"lat":-12.0,"elevation_m":-4770.1,"slope_deg":1.96,"slope_class":"easy_walk",...}`.

If uvicorn fails with `ModuleNotFoundError`, install the deps into the team venv: `"$TEAM_REPO/backend/.venv/bin/pip" install -r /Users/sielprar/PycharmProjects/NASA/mars-backend/backend/requirements.txt`.

Leave the backend running for Task 13. (Commit happens in Task 1, once the repo exists.)

---

### Task 1: Scaffold the Vite + React + Leaflet app with Vitest

**Files:**
- Create: `package.json`, `vite.config.js`, `index.html`, `.gitignore`, `src/main.jsx`, `src/App.jsx`, `src/index.css`, `src/App.css`, `src/test/setup.js`, `src/test/reactLeafletMock.jsx`, `src/test/fixtures.js`

All paths are relative to `/Users/sielprar/PycharmProjects/Nasa web`.

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "mars-map-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "leaflet": "^1.9.4",
    "react": "^19.3.1",
    "react-dom": "^19.3.1",
    "react-leaflet": "^5.0.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^6.1.2",
    "vite": "^8.3.6"
  }
}
```

(These versions match the team repo's `frontend/package.json`.)

- [ ] **Step 2: Install dependencies and the test tooling**

```bash
cd "/Users/sielprar/PycharmProjects/Nasa web"
npm install
npm install -D vitest jsdom @testing-library/react @testing-library/dom @testing-library/jest-dom
```

If npm reports a peer conflict between `vitest` and `vite`, check `npm view vitest peerDependencies` and install the vitest major that accepts `vite@^8`.

- [ ] **Step 3: Write `vite.config.js`**

```js
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    // Leaflet cannot draw vector layers in jsdom; every test gets a lightweight react-leaflet double.
    alias: {
      'react-leaflet': fileURLToPath(new URL('./src/test/reactLeafletMock.jsx', import.meta.url)),
    },
  },
})
```

- [ ] **Step 4: Write `index.html`, `.gitignore`, entry and placeholder app**

`index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mars Map</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

`.gitignore`:

```
node_modules/
dist/
.DS_Store
```

`src/main.jsx`:

```jsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

`src/App.jsx` (placeholder; Task 12 replaces it):

```jsx
export default function App() {
  return <h1>Mars Map</h1>
}
```

`src/index.css`:

```css
:root {
  color-scheme: dark;
  --panel-bg: rgba(22, 17, 15, 0.92);
  --panel-border: rgba(255, 255, 255, 0.08);
  --text: #f2ece6;
  --muted: #b3a79c;
  --accent: #e07a4f;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  color: var(--text);
}

* {
  box-sizing: border-box;
}

html,
body,
#root {
  height: 100%;
  margin: 0;
}

body {
  background: #120e0c;
}
```

`src/App.css`: create it empty for now (Task 12 fills it).

- [ ] **Step 5: Write the test setup, react-leaflet mock and fixtures**

`src/test/setup.js`:

```js
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => cleanup())
```

`src/test/reactLeafletMock.jsx`:

```jsx
// Test double for react-leaflet (aliased in vite.config.js `test.alias`).
// Each component renders a <div> that exposes its key props as data attributes.

// Handlers registered through useMapEvents, so tests can fire map events:
//   act(() => mapEventHandlers.click({ latlng: { lat: -12, lng: -70 } }))
export const mapEventHandlers = {}

export function useMapEvents(handlers) {
  Object.assign(mapEventHandlers, handlers)
  return null
}

export function MapContainer({ children, className }) {
  return (
    <div data-testid="map" className={className}>
      {children}
    </div>
  )
}

export function ZoomControl() {
  return null
}

export function TileLayer({ url, opacity = 1, tileSize, maxNativeZoom, zIndex }) {
  return (
    <div
      data-testid="tile-layer"
      data-url={url}
      data-opacity={opacity}
      data-tile-size={tileSize}
      data-max-native-zoom={maxNativeZoom}
      data-z-index={zIndex}
    />
  )
}

export function ImageOverlay({ url, opacity = 1 }) {
  return <div data-testid="image-overlay" data-url={url} data-opacity={opacity} />
}

export function GeoJSON({ data }) {
  return <div data-testid="geojson" data-count={data.features.length} />
}
```

`src/test/fixtures.js`:

```js
import { vi } from 'vitest'

export const BOUNDS = [
  [-13.4, -71.8],
  [-10.0, -68.0],
]

const source = (id, title, extra = {}) => ({
  id,
  title,
  tile_url: `/api/tiles/${id}/{z}/{y}/{x}`,
  format: 'png',
  tile_size: 256,
  min_zoom: 5,
  max_zoom: 9,
  bounds: BOUNDS,
  coverage_note: `${title} coverage`,
  ...extra,
})

export const layerOne = {
  layer: 'base_imagery',
  default_source: 'ctx_coprates',
  sources: [
    source('ctx_coprates', 'CTX mosaic, Coprates / East Melas'),
    source('ctx_global', 'CTX global mosaic (fallback)', { tile_size: 512 }),
    source('hirise', 'HiRISE (zoom-in detail)', { tile_size: 512 }),
  ],
}

export const layerTwo = {
  layer: 'relief',
  bounds: BOUNDS,
  resolution_m: 186,
  elevation_range_m: [-5401, 4596],
  slope_classes: [
    { id: 'easy_walk', label: 'Easy walk', min_deg: 0, max_deg: 5, color: '#1a9850', walkable: true, vehicle: true },
    { id: 'walkable', label: 'Walkable', min_deg: 5, max_deg: 15, color: '#91cf60', walkable: true, vehicle: true },
    { id: 'vehicle_only', label: 'Vehicle only', min_deg: 15, max_deg: 25, color: '#fee08b', walkable: false, vehicle: true },
    { id: 'vehicle_limit', label: 'Hard / vehicle limit', min_deg: 25, max_deg: 35, color: '#fc8d59', walkable: false, vehicle: true },
    { id: 'impassable', label: 'Impassable', min_deg: 35, max_deg: 90, color: '#d73027', walkable: false, vehicle: false },
  ],
  overlay: { url: '/api/get-layer-two/walkability.png', bounds: BOUNDS },
  hillshade_sources: [
    source('hillshade_color', 'MOLA + HRSC colour shaded relief', { format: 'jpg', max_zoom: 8 }),
    source('hillshade_ctx', 'CTX shaded relief, East Melas'),
  ],
  caveats: [
    'The 200 m elevation grid underestimates local slope.',
    'Slope class thresholds are provisional.',
  ],
}

export const layerThree = {
  type: 'FeatureCollection',
  layer: 'poi',
  categories: {
    mineral: 1,
    water_activity: 0,
    exploration_zone: 1,
    dunes: 0,
    geology: 0,
    place_name: 0,
    observation: 0,
  },
  overlays: [source('crism_sulfate', 'CRISM polyhydrated sulfate indicator')],
  features: [
    {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-68.46, -12.09] },
      properties: {
        id: 'aq:302',
        category: 'mineral',
        name: 'Silica detection',
        description: 'Orbital detection of silica.',
        source: 'Aqueous Mineral Distribution (NASA Trek)',
        raw: {},
      },
    },
    {
      type: 'Feature',
      geometry: {
        type: 'Polygon',
        coordinates: [[[-70, -10.3], [-69.5, -10.3], [-69.5, -10.8], [-70, -10.8], [-70, -10.3]]],
      },
      properties: {
        id: 'ez:1',
        category: 'exploration_zone',
        name: 'Melas exploration zone boundary',
        description: 'Candidate human exploration zone.',
        source: 'NASA Human Exploration Zones (NASA Trek)',
        raw: {},
      },
    },
  ],
}

const SEASON_NAMES = {
  autumn: 'S. Autumn (Ls 0-90)',
  winter: 'S. Winter (Ls 90-180)',
  spring: 'S. Spring (Ls 180-270, perihelion)',
  summer: 'S. Summer (Ls 270-360)',
}

const cell = (lon, lat, properties) => ({
  type: 'Feature',
  geometry: {
    type: 'Polygon',
    coordinates: [[[lon, lat], [lon + 1, lat], [lon + 1, lat + 1], [lon, lat + 1], [lon, lat]]],
  },
  properties,
})

export function layerFour(season = 'spring') {
  const name = SEASON_NAMES[season]
  return {
    type: 'FeatureCollection',
    layer: 'weather',
    season,
    season_name: name,
    caveat: 'Values are historical frequencies, not forecasts.',
    legend: { Low: '#2e7d32', Moderate: '#f9a825', High: '#c62828' },
    aoi_summary: {
      confidence: 'approximate',
      message: `APPROXIMATE: not enough data to reliably calculate the risk for the demo area in ${name}.`,
    },
    features: [
      cell(-71, -13, {
        season: name,
        confidence: 'reliable',
        display_risk: 'Low',
        display_style: 'solid',
        message: 'Low risk: 0.2 storm-days per Mars year.',
      }),
      cell(-70, -13, {
        season: name,
        confidence: 'approximate',
        display_risk: 'High',
        display_style: 'hatched',
        message: 'APPROXIMATE: not enough data to reliably calculate the risk for this area.',
      }),
      cell(-69, -13, {
        season: name,
        confidence: 'insufficient_data',
        display_risk: null,
        display_style: 'grey',
        message: 'NOT ENOUGH DATA: risk cannot be reliably calculated for this area. No estimate possible.',
      }),
    ],
  }
}

export const pointInfo = {
  lon: -70,
  lat: -12,
  elevation_m: -4770.1,
  slope_deg: 1.96,
  slope_class: 'easy_walk',
  walkable: true,
  vehicle: true,
  approximate: true,
}

export function jsonResponse(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body }
}

// fetch double: routes map a path prefix to a JSON body or to (path) => response. Longest prefix wins.
export function routeFetch(routes) {
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length)
  return vi.fn(async (url) => {
    const path = String(url)
    const key = keys.find((k) => path.startsWith(k))
    if (!key) return jsonResponse({ detail: 'Not Found' }, 404)
    const route = routes[key]
    return typeof route === 'function' ? route(path) : jsonResponse(route)
  })
}
```

- [ ] **Step 6: Check that the build and test runner work**

```bash
npm run build
```

Expected: `✓ built in …` with no errors.

```bash
npx vitest run --passWithNoTests
```

Expected: `No test files found, exiting with code 0`.

- [ ] **Step 7: Init git and commit**

```bash
cd "/Users/sielprar/PycharmProjects/Nasa web"
git init
git add .gitignore package.json package-lock.json vite.config.js index.html src scripts docs
git commit -m "chore: scaffold Vite + React + Leaflet app with Vitest"
```

---

### Task 2: Map configuration and coordinate formatting

**Files:**
- Create: `src/config/map.js`, `src/config/map.test.js`, `src/config/layers.js`

- [ ] **Step 1: Write the failing test**

`src/config/map.test.js`:

```js
import { expect, test } from 'vitest'
import { AOI_BOUNDS, MAP_CENTER, MAX_BOUNDS, formatLatLng } from './map.js'

test('AOI bounds are Leaflet order [[south, west], [north, east]]', () => {
  expect(AOI_BOUNDS).toEqual([
    [-13.4, -71.8],
    [-10.0, -68.0],
  ])
})

test('map centre is the middle of the AOI', () => {
  expect(MAP_CENTER[0]).toBeCloseTo(-11.7)
  expect(MAP_CENTER[1]).toBeCloseTo(-69.9)
})

test('max bounds contain the AOI and the whole weather grid', () => {
  const [[s, w], [n, e]] = MAX_BOUNDS
  expect(s).toBeLessThanOrEqual(-30)
  expect(w).toBeLessThanOrEqual(-90)
  expect(n).toBeGreaterThanOrEqual(10)
  expect(e).toBeGreaterThanOrEqual(-50)
})

test('formatLatLng writes south/west for negative values', () => {
  expect(formatLatLng(-11.7, -69.9)).toBe('11.700° S, 69.900° W')
})

test('formatLatLng writes north/east for positive values', () => {
  expect(formatLatLng(4.5, 137.4)).toBe('4.500° N, 137.400° E')
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/config/map.test.js`
Expected: FAIL with `Failed to resolve import "./map.js"`.

- [ ] **Step 3: Implement `src/config/map.js`**

```js
// Demo area (East Melas / Coprates Chasma). Same box as the backend's AOI.
export const AOI = { west: -71.8, south: -13.4, east: -68.0, north: -10.0 }

export const AOI_BOUNDS = [
  [AOI.south, AOI.west],
  [AOI.north, AOI.east],
]

export const MAP_CENTER = [(AOI.south + AOI.north) / 2, (AOI.west + AOI.east) / 2]

// Tiles exist for zooms 5–9; Leaflet scales them outside that range.
export const MAP_ZOOM = { initial: 7, min: 4, max: 12 }

// The dust-storm grid spans lon -90..-50, lat -30..10; keep panning near it.
export const MAX_BOUNDS = [
  [-35, -95],
  [15, -45],
]

// Every Trek tile covers one 256 px cell, even when the image itself is 512 px.
export const TILE_DISPLAY_SIZE = 256

// Shown where a tile is missing, instead of a broken-image icon.
export const TRANSPARENT_TILE =
  'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'

export function formatLatLng(lat, lng) {
  const ns = lat < 0 ? 'S' : 'N'
  const ew = lng < 0 ? 'W' : 'E'
  return `${Math.abs(lat).toFixed(3)}° ${ns}, ${Math.abs(lng).toFixed(3)}° ${ew}`
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/config/map.test.js`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the layer configuration (constants only, no logic to test)**

`src/config/layers.js`:

```js
// Points-of-interest categories, in the backend's order (app/layers/poi/normalize.py CATEGORIES).
export const POI_CATEGORIES = [
  { id: 'mineral', label: 'Minerals', color: '#00bcd4' },
  { id: 'water_activity', label: 'Water activity', color: '#2979ff' },
  { id: 'exploration_zone', label: 'Exploration zones', color: '#ffd600' },
  { id: 'dunes', label: 'Dune fields', color: '#ff9100' },
  { id: 'geology', label: 'Geology units', color: '#ab47bc' },
  { id: 'place_name', label: 'Place names', color: '#ffffff' },
  { id: 'observation', label: 'CRISM observations', color: '#76ff03' },
]

// Values accepted by /api/get-layer-four?season=
export const SEASONS = [
  { id: 'autumn', label: 'Southern autumn (Ls 0–90)' },
  { id: 'winter', label: 'Southern winter (Ls 90–180)' },
  { id: 'spring', label: 'Southern spring (Ls 180–270, perihelion)' },
  { id: 'summer', label: 'Southern summer (Ls 270–360)' },
]

export const SULFATE_SOURCE_ID = 'crism_sulfate'

export const LAYER_OPACITY = { hillshade: 0.6, walkability: 0.55, sulfate: 0.7 }

// Everything the user can toggle. baseSource null = use the backend's default_source.
export const DEFAULT_VIEW = {
  baseSource: null,
  hillshadeSource: null,
  walkability: false,
  poi: true,
  poiCategories: POI_CATEGORIES.map((c) => c.id),
  sulfate: false,
  weather: false,
  season: 'spring',
}
```

- [ ] **Step 6: Commit**

```bash
git add src/config
git commit -m "feat: add map and layer configuration"
```

---

### Task 3: HTML escaping for popups

**Files:**
- Create: `src/utils/html.js`, `src/utils/html.test.js`

- [ ] **Step 1: Write the failing test**

`src/utils/html.test.js`:

```js
import { expect, test } from 'vitest'
import { escapeHtml } from './html.js'

test('escapes the five HTML special characters', () => {
  expect(escapeHtml(`<a href="x">&'</a>`)).toBe('&lt;a href=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;')
})

test('turns null and undefined into an empty string', () => {
  expect(escapeHtml(null)).toBe('')
  expect(escapeHtml(undefined)).toBe('')
})

test('stringifies numbers', () => {
  expect(escapeHtml(42)).toBe('42')
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/utils/html.test.js`
Expected: FAIL with `Failed to resolve import "./html.js"`.

- [ ] **Step 3: Implement `src/utils/html.js`**

```js
const ENTITIES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }

// Leaflet popups take raw HTML; every value from the API goes through this first.
export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ENTITIES[ch])
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/utils/html.test.js`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/utils
git commit -m "feat: add escapeHtml for popup content"
```

---

### Task 4: API client

**Files:**
- Create: `src/api/marsApi.js`, `src/api/marsApi.test.js`

- [ ] **Step 1: Write the failing test**

`src/api/marsApi.test.js`:

```js
import { afterEach, expect, test, vi } from 'vitest'
import { jsonResponse, layerOne, pointInfo } from '../test/fixtures.js'
import { ApiError, getBaseImagery, getPointInfo, getPois, getRelief, getWeather } from './marsApi.js'

afterEach(() => vi.unstubAllGlobals())

function stubFetch(response) {
  const fetch = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

test('getBaseImagery returns layer one JSON', async () => {
  const fetch = stubFetch(jsonResponse(layerOne))
  await expect(getBaseImagery()).resolves.toEqual(layerOne)
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-one')
})

test('getRelief and getPois call layers two and three', async () => {
  const fetch = stubFetch(jsonResponse({}))
  await getRelief()
  await getPois()
  expect(fetch).toHaveBeenNthCalledWith(1, '/api/get-layer-two')
  expect(fetch).toHaveBeenNthCalledWith(2, '/api/get-layer-three')
})

test('getWeather sends the season as a query parameter', async () => {
  const fetch = stubFetch(jsonResponse({}))
  await getWeather('winter')
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-four?season=winter')
})

test('getPointInfo sends lon and lat', async () => {
  const fetch = stubFetch(jsonResponse(pointInfo))
  await expect(getPointInfo(-11.7, -69.9)).resolves.toEqual(pointInfo)
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-two/point?lon=-69.9&lat=-11.7')
})

test('a 503 becomes an ApiError with the backend detail and fix', async () => {
  stubFetch(jsonResponse({ detail: 'Weather files not found', fix: 'python scripts/build_weather/build_weather.py' }, 503))
  const error = await getWeather('spring').catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.message).toBe('Weather files not found')
  expect(error.status).toBe(503)
  expect(error.fix).toBe('python scripts/build_weather/build_weather.py')
})

test('a non-string detail (FastAPI validation error) falls back to a generic message', async () => {
  stubFetch(jsonResponse({ detail: [{ msg: 'field required' }] }, 422))
  const error = await getWeather('x').catch((e) => e)
  expect(error.message).toBe('Request failed (422)')
  expect(error.fix).toBeNull()
})

test('a network failure becomes an ApiError with status 0', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  const error = await getBaseImagery().catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(0)
  expect(error.message).toMatch(/backend is not reachable/i)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/api/marsApi.test.js`
Expected: FAIL with `Failed to resolve import "./marsApi.js"`.

- [ ] **Step 3: Implement `src/api/marsApi.js`**

```js
// The only module that talks to the backend. Paths are relative; Vite proxies /api to :8000.

export class ApiError extends Error {
  constructor(message, { status = 0, fix = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fix = fix // shell command the backend suggests when a layer's data is missing (HTTP 503)
  }
}

async function getJson(path) {
  let response
  try {
    response = await fetch(path)
  } catch {
    throw new ApiError('The backend is not reachable. Start it on port 8000 (scripts/dev-backend.sh).')
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new ApiError(message, { status: response.status, fix: body.fix ?? null })
  }
  return body
}

export const getBaseImagery = () => getJson('/api/get-layer-one')

export const getRelief = () => getJson('/api/get-layer-two')

export const getPois = () => getJson('/api/get-layer-three')

export const getWeather = (season) => getJson(`/api/get-layer-four?${new URLSearchParams({ season })}`)

export const getPointInfo = (lat, lng) =>
  getJson(`/api/get-layer-two/point?${new URLSearchParams({ lon: String(lng), lat: String(lat) })}`)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/api/marsApi.test.js`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/api
git commit -m "feat: add backend API client with ApiError"
```

---

### Task 5: `useLayer` data-loading hook

**Files:**
- Create: `src/hooks/useLayer.js`, `src/hooks/useLayer.test.jsx`

- [ ] **Step 1: Write the failing test**

`src/hooks/useLayer.test.jsx`:

```jsx
import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../api/marsApi.js'
import { useLayer } from './useLayer.js'

test('loads data when enabled', async () => {
  const load = vi.fn().mockResolvedValue({ a: 1 })
  const { result } = renderHook(() => useLayer(load, []))
  expect(result.current.status).toBe('loading')
  await waitFor(() => expect(result.current.status).toBe('ready'))
  expect(result.current.data).toEqual({ a: 1 })
  expect(load).toHaveBeenCalledTimes(1)
})

test('stays idle and does not load when disabled', () => {
  const load = vi.fn()
  const { result } = renderHook(() => useLayer(load, [], false))
  expect(result.current.status).toBe('idle')
  expect(load).not.toHaveBeenCalled()
})

test('reports errors', async () => {
  const load = vi.fn().mockRejectedValue(new ApiError('Weather files not found', { status: 503 }))
  const { result } = renderHook(() => useLayer(load, []))
  await waitFor(() => expect(result.current.status).toBe('error'))
  expect(result.current.error.message).toBe('Weather files not found')
  expect(result.current.data).toBeNull()
})

test('reloads when deps change and ignores the stale response', async () => {
  const resolvers = {}
  const load = vi.fn((season) => new Promise((resolve) => (resolvers[season] = resolve)))
  const { result, rerender } = renderHook(({ season }) => useLayer(() => load(season), [season]), {
    initialProps: { season: 'spring' },
  })
  rerender({ season: 'winter' })
  await act(async () => resolvers.winter('W'))
  await act(async () => resolvers.spring('S'))
  expect(result.current.data).toBe('W')
  expect(load).toHaveBeenCalledTimes(2)
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/hooks/useLayer.test.jsx`
Expected: FAIL with `Failed to resolve import "./useLayer.js"`.

- [ ] **Step 3: Implement `src/hooks/useLayer.js`**

```js
import { useEffect, useState } from 'react'

/**
 * Loads one layer's data. Re-runs `load` whenever `enabled` or any value in `deps` changes.
 * Returns { status: 'idle' | 'loading' | 'ready' | 'error', data, error }.
 * While reloading, the previous data stays available, so the map does not flash empty.
 */
export function useLayer(load, deps, enabled = true) {
  const [state, setState] = useState({ status: enabled ? 'loading' : 'idle', data: null, error: null })

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    setState((prev) => ({ status: 'loading', data: prev.data, error: null }))
    load().then(
      (data) => !cancelled && setState({ status: 'ready', data, error: null }),
      (error) => !cancelled && setState({ status: 'error', data: null, error }),
    )
    return () => {
      cancelled = true
    }
    // `load` is usually an inline arrow; the caller lists what it depends on in `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  return state
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/hooks/useLayer.test.jsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/hooks
git commit -m "feat: add useLayer hook for on-demand layer loading"
```

---

### Task 6: The map shell (`MarsMap`) and cursor coordinates

**Files:**
- Create: `src/features/map/CoordinateReadout/CoordinateReadout.jsx`, `src/features/map/CoordinateReadout/CoordinateReadout.test.jsx`, `src/features/map/MarsMap/MarsMap.jsx`, `src/features/map/MarsMap/MarsMap.test.jsx`

- [ ] **Step 1: Write the failing tests**

`src/features/map/CoordinateReadout/CoordinateReadout.test.jsx`:

```jsx
import { act, render, screen } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { expect, test } from 'vitest'
import CoordinateReadout from './CoordinateReadout.jsx'

test('shows the cursor position and hides it when the cursor leaves the map', () => {
  render(<CoordinateReadout />)
  expect(screen.queryByText(/°/)).toBeNull()

  act(() => mapEventHandlers.mousemove({ latlng: { lat: -11.7, lng: -69.9 } }))
  expect(screen.getByText('11.700° S, 69.900° W')).toBeInTheDocument()

  act(() => mapEventHandlers.mouseout())
  expect(screen.queryByText(/°/)).toBeNull()
})
```

`src/features/map/MarsMap/MarsMap.test.jsx`:

```jsx
import { act, render, screen } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { expect, test, vi } from 'vitest'
import MarsMap from './MarsMap.jsx'

test('renders its children inside the map', () => {
  render(
    <MarsMap>
      <span>layer goes here</span>
    </MarsMap>,
  )
  expect(screen.getByTestId('map')).toContainElement(screen.getByText('layer goes here'))
})

test('forwards map clicks as lat/lng', () => {
  const onMapClick = vi.fn()
  render(<MarsMap onMapClick={onMapClick} />)
  act(() => mapEventHandlers.click({ latlng: { lat: -11.7, lng: -69.9 } }))
  expect(onMapClick).toHaveBeenCalledWith({ lat: -11.7, lng: -69.9 })
})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npx vitest run src/features/map`
Expected: FAIL with `Failed to resolve import "./CoordinateReadout.jsx"` and `"./MarsMap.jsx"`.

- [ ] **Step 3: Implement `CoordinateReadout.jsx`**

```jsx
import { useState } from 'react'
import { useMapEvents } from 'react-leaflet'
import { formatLatLng } from '../../../config/map.js'

// Rendered inside MapContainer so that cursor moves re-render only this component, not the whole app.
export default function CoordinateReadout() {
  const [latlng, setLatlng] = useState(null)
  useMapEvents({
    mousemove: (event) => setLatlng(event.latlng),
    mouseout: () => setLatlng(null),
  })
  if (!latlng) return null
  return <div className="coordinate-readout">{formatLatLng(latlng.lat, latlng.lng)}</div>
}
```

- [ ] **Step 4: Implement `MarsMap.jsx`**

```jsx
import L from 'leaflet'
import { MapContainer, ZoomControl, useMapEvents } from 'react-leaflet'
import { MAP_CENTER, MAP_ZOOM, MAX_BOUNDS } from '../../../config/map.js'
import CoordinateReadout from '../CoordinateReadout/CoordinateReadout.jsx'

function ClickEvents({ onClick }) {
  useMapEvents({ click: (event) => onClick?.(event.latlng) })
  return null
}

// Mars tiles are plain lat/lon (equirectangular), so the map uses EPSG:4326, not Web Mercator.
// No scale control: Leaflet's assumes Earth's radius.
export default function MarsMap({ onMapClick, children }) {
  return (
    <MapContainer
      className="mars-map"
      crs={L.CRS.EPSG4326}
      center={MAP_CENTER}
      zoom={MAP_ZOOM.initial}
      minZoom={MAP_ZOOM.min}
      maxZoom={MAP_ZOOM.max}
      maxBounds={MAX_BOUNDS}
      maxBoundsViscosity={0.8}
      zoomControl={false}
    >
      <ZoomControl position="bottomright" />
      <ClickEvents onClick={onMapClick} />
      <CoordinateReadout />
      {children}
    </MapContainer>
  )
}
```

- [ ] **Step 5: Run them to verify they pass**

Run: `npx vitest run src/features/map`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/features/map
git commit -m "feat: add EPSG:4326 Mars map shell with cursor coordinates"
```

---

### Task 7: `TrekTileLayer` (shared tile layer for imagery, hillshade, sulfate)

**Files:**
- Create: `src/features/layers/TrekTileLayer/TrekTileLayer.jsx`, `src/features/layers/TrekTileLayer/TrekTileLayer.test.jsx`

- [ ] **Step 1: Write the failing test**

`src/features/layers/TrekTileLayer/TrekTileLayer.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerOne } from '../../../test/fixtures.js'
import TrekTileLayer from './TrekTileLayer.jsx'

const [ctxCoprates, ctxGlobal] = layerOne.sources

test('uses the source tile URL and native zoom range', () => {
  render(<TrekTileLayer source={ctxCoprates} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/ctx_coprates/{z}/{y}/{x}')
  expect(tile.dataset.maxNativeZoom).toBe('9')
  expect(tile.dataset.opacity).toBe('1')
})

test('always displays tiles at 256 px, even for 512 px sources', () => {
  render(<TrekTileLayer source={ctxGlobal} />)
  expect(screen.getByTestId('tile-layer').dataset.tileSize).toBe('256')
})

test('passes opacity and z-index through', () => {
  render(<TrekTileLayer source={ctxCoprates} opacity={0.6} zIndex={2} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.opacity).toBe('0.6')
  expect(tile.dataset.zIndex).toBe('2')
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/features/layers/TrekTileLayer`
Expected: FAIL with `Failed to resolve import "./TrekTileLayer.jsx"`.

- [ ] **Step 3: Implement `TrekTileLayer.jsx`**

```jsx
import { TileLayer } from 'react-leaflet'
import { MAP_ZOOM, TILE_DISPLAY_SIZE, TRANSPARENT_TILE } from '../../../config/map.js'

export const TREK_ATTRIBUTION = 'Imagery: NASA Solar System Treks'

// One backend TileSource (from /api/get-layer-*) as a Leaflet tile layer.
// key={source.id} remounts the layer when the source changes, because Leaflet keeps most options fixed after creation.
export default function TrekTileLayer({ source, opacity = 1, zIndex = 1 }) {
  return (
    <TileLayer
      key={source.id}
      url={source.tile_url}
      tileSize={TILE_DISPLAY_SIZE}
      minNativeZoom={source.min_zoom}
      maxNativeZoom={source.max_zoom}
      minZoom={MAP_ZOOM.min}
      maxZoom={MAP_ZOOM.max}
      bounds={source.bounds}
      errorTileUrl={TRANSPARENT_TILE}
      opacity={opacity}
      zIndex={zIndex}
      attribution={TREK_ATTRIBUTION}
    />
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/features/layers/TrekTileLayer`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/features/layers/TrekTileLayer
git commit -m "feat: add TrekTileLayer for backend tile sources"
```

---

### Task 8: Relief layer (hillshade + walkability)

**Files:**
- Create: `src/features/layers/ReliefLayer/ReliefLayer.jsx`, `src/features/layers/ReliefLayer/ReliefLayer.test.jsx`

- [ ] **Step 1: Write the failing test**

`src/features/layers/ReliefLayer/ReliefLayer.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerTwo } from '../../../test/fixtures.js'
import ReliefLayer from './ReliefLayer.jsx'

test('renders nothing when hillshade and walkability are off', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource={null} showWalkability={false} />)
  expect(screen.queryByTestId('tile-layer')).toBeNull()
  expect(screen.queryByTestId('image-overlay')).toBeNull()
})

test('renders the chosen hillshade source as semi-transparent tiles', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource="hillshade_color" showWalkability={false} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/hillshade_color/{z}/{y}/{x}')
  expect(tile.dataset.opacity).toBe('0.6')
})

test('renders the walkability PNG as an image overlay', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource={null} showWalkability />)
  expect(screen.getByTestId('image-overlay').dataset.url).toBe('/api/get-layer-two/walkability.png')
})

test('ignores an unknown hillshade id', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource="nope" showWalkability={false} />)
  expect(screen.queryByTestId('tile-layer')).toBeNull()
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/features/layers/ReliefLayer`
Expected: FAIL with `Failed to resolve import "./ReliefLayer.jsx"`.

- [ ] **Step 3: Implement `ReliefLayer.jsx`**

```jsx
import { ImageOverlay } from 'react-leaflet'
import { LAYER_OPACITY } from '../../../config/layers.js'
import TrekTileLayer from '../TrekTileLayer/TrekTileLayer.jsx'

// Layer 2. `relief` is the /api/get-layer-two response.
export default function ReliefLayer({ relief, hillshadeSource, showWalkability }) {
  const hillshade = relief.hillshade_sources.find((s) => s.id === hillshadeSource)
  return (
    <>
      {hillshade && <TrekTileLayer source={hillshade} opacity={LAYER_OPACITY.hillshade} zIndex={2} />}
      {showWalkability && (
        <ImageOverlay
          url={relief.overlay.url}
          bounds={relief.overlay.bounds}
          opacity={LAYER_OPACITY.walkability}
          className="walkability-overlay"
        />
      )}
    </>
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/features/layers/ReliefLayer`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/features/layers/ReliefLayer
git commit -m "feat: add relief layer with hillshade and walkability overlay"
```

---

### Task 9: Points-of-interest layer

**Files:**
- Create: `src/features/layers/PoiLayer/poiHelpers.js`, `src/features/layers/PoiLayer/poiHelpers.test.js`, `src/features/layers/PoiLayer/PoiLayer.jsx`, `src/features/layers/PoiLayer/PoiLayer.test.jsx`

- [ ] **Step 1: Write the failing helper test**

`src/features/layers/PoiLayer/poiHelpers.test.js`:

```js
import { expect, test } from 'vitest'
import { layerThree } from '../../../test/fixtures.js'
import { categoryInfo, filterPois, poiMarkerStyle, poiPathStyle, poiPopupHtml } from './poiHelpers.js'

const [mineral, zone] = layerThree.features

test('categoryInfo returns label and colour of a known category', () => {
  expect(categoryInfo('mineral')).toEqual({ id: 'mineral', label: 'Minerals', color: '#00bcd4' })
})

test('categoryInfo falls back to grey for an unknown category', () => {
  expect(categoryInfo('mystery')).toEqual({ id: 'mystery', label: 'mystery', color: '#9e9e9e' })
})

test('point markers are filled with the category colour', () => {
  expect(poiMarkerStyle(mineral)).toMatchObject({ fillColor: '#00bcd4', radius: 7 })
})

test('polygons are outlined in the category colour with a light fill', () => {
  expect(poiPathStyle(zone)).toMatchObject({ color: '#ffd600', fillColor: '#ffd600', fillOpacity: 0.12 })
})

test('popup shows name, category, description and source, escaped', () => {
  const html = poiPopupHtml({ ...mineral.properties, name: '<b>Silica</b>' })
  expect(html).toContain('&lt;b&gt;Silica&lt;/b&gt;')
  expect(html).toContain('Minerals')
  expect(html).toContain('Orbital detection of silica.')
  expect(html).toContain('Aqueous Mineral Distribution (NASA Trek)')
})

test('filterPois keeps only the chosen categories', () => {
  expect(filterPois(layerThree, ['mineral']).features).toEqual([mineral])
  expect(filterPois(layerThree, []).features).toEqual([])
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/features/layers/PoiLayer/poiHelpers.test.js`
Expected: FAIL with `Failed to resolve import "./poiHelpers.js"`.

- [ ] **Step 3: Implement `poiHelpers.js`**

```js
import { POI_CATEGORIES } from '../../../config/layers.js'
import { escapeHtml } from '../../../utils/html.js'

const FALLBACK_COLOR = '#9e9e9e'

export function categoryInfo(id) {
  return POI_CATEGORIES.find((c) => c.id === id) ?? { id, label: id, color: FALLBACK_COLOR }
}

export function poiMarkerStyle(feature) {
  const { color } = categoryInfo(feature.properties.category)
  return { radius: 7, color: '#1b1b1b', weight: 1.5, fillColor: color, fillOpacity: 0.95 }
}

export function poiPathStyle(feature) {
  const { color } = categoryInfo(feature.properties.category)
  return { color, weight: 2, fillColor: color, fillOpacity: 0.12 }
}

export function poiPopupHtml(props) {
  return [
    '<div class="popup">',
    `<strong>${escapeHtml(props.name)}</strong>`,
    `<div class="popup-meta">${escapeHtml(categoryInfo(props.category).label)}</div>`,
    `<p>${escapeHtml(props.description)}</p>`,
    `<small>${escapeHtml(props.source)}</small>`,
    '</div>',
  ].join('')
}

export function filterPois(collection, categories) {
  const wanted = new Set(categories)
  return {
    type: 'FeatureCollection',
    features: collection.features.filter((f) => wanted.has(f.properties.category)),
  }
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/features/layers/PoiLayer/poiHelpers.test.js`
Expected: PASS (6 tests).

- [ ] **Step 5: Write the failing component test**

`src/features/layers/PoiLayer/PoiLayer.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { POI_CATEGORIES } from '../../../config/layers.js'
import { layerThree } from '../../../test/fixtures.js'
import PoiLayer from './PoiLayer.jsx'

const ALL = POI_CATEGORIES.map((c) => c.id)

test('shows every feature when all categories are on', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers showSulfate={false} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('2')
})

test('shows only the chosen categories', () => {
  render(<PoiLayer pois={layerThree} categories={['mineral']} showMarkers showSulfate={false} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('1')
})

test('hides the features when markers are off', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers={false} showSulfate={false} />)
  expect(screen.queryByTestId('geojson')).toBeNull()
})

test('shows the CRISM sulfate tiles when asked', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers={false} showSulfate />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/crism_sulfate/{z}/{y}/{x}')
  expect(tile.dataset.opacity).toBe('0.7')
})
```

- [ ] **Step 6: Run it to verify it fails**

Run: `npx vitest run src/features/layers/PoiLayer/PoiLayer.test.jsx`
Expected: FAIL with `Failed to resolve import "./PoiLayer.jsx"`.

- [ ] **Step 7: Implement `PoiLayer.jsx`**

```jsx
import L from 'leaflet'
import { useMemo } from 'react'
import { GeoJSON } from 'react-leaflet'
import { LAYER_OPACITY, SULFATE_SOURCE_ID } from '../../../config/layers.js'
import TrekTileLayer from '../TrekTileLayer/TrekTileLayer.jsx'
import { filterPois, poiMarkerStyle, poiPathStyle, poiPopupHtml } from './poiHelpers.js'

const pointToLayer = (feature, latlng) => L.circleMarker(latlng, poiMarkerStyle(feature))
const onEachFeature = (feature, layer) => layer.bindPopup(poiPopupHtml(feature.properties))

// Layer 3. `pois` is the /api/get-layer-three response.
export default function PoiLayer({ pois, categories, showMarkers, showSulfate }) {
  const data = useMemo(() => filterPois(pois, categories), [pois, categories])
  const sulfate = pois.overlays.find((o) => o.id === SULFATE_SOURCE_ID)
  return (
    <>
      {showSulfate && sulfate && <TrekTileLayer source={sulfate} opacity={LAYER_OPACITY.sulfate} zIndex={3} />}
      {showMarkers && (
        // react-leaflet's GeoJSON ignores new `data` after mount; the key forces a rebuild when the filter changes.
        <GeoJSON
          key={categories.join(',')}
          data={data}
          style={poiPathStyle}
          pointToLayer={pointToLayer}
          onEachFeature={onEachFeature}
        />
      )}
    </>
  )
}
```

- [ ] **Step 8: Run all POI tests to verify they pass**

Run: `npx vitest run src/features/layers/PoiLayer`
Expected: PASS (10 tests).

- [ ] **Step 9: Commit**

```bash
git add src/features/layers/PoiLayer
git commit -m "feat: add points-of-interest layer with category filter and sulfate overlay"
```

---

### Task 10: Dust-storm (weather) layer

**Files:**
- Create: `src/features/layers/WeatherLayer/weatherHelpers.js`, `src/features/layers/WeatherLayer/weatherHelpers.test.js`, `src/features/layers/WeatherLayer/HatchPatterns.jsx`, `src/features/layers/WeatherLayer/HatchPatterns.test.jsx`, `src/features/layers/WeatherLayer/WeatherLayer.jsx`, `src/features/layers/WeatherLayer/WeatherLayer.test.jsx`

How the hatching works: Leaflet's SVG renderer writes `fillColor` straight into the path's `fill` attribute. If `fillColor` is `url(#hatch-High)`, the cell is filled with the SVG `<pattern id="hatch-High">` that `HatchPatterns` renders somewhere in the page (pattern ids are global to the document).

- [ ] **Step 1: Write the failing helper test**

`src/features/layers/WeatherLayer/weatherHelpers.test.js`:

```js
import { expect, test } from 'vitest'
import { layerFour } from '../../../test/fixtures.js'
import { INSUFFICIENT_COLOR, hatchId, weatherCellStyle, weatherPopupHtml } from './weatherHelpers.js'

const weather = layerFour('spring')
const [reliable, approximate, insufficient] = weather.features

test('reliable cells are filled solid with the risk colour', () => {
  expect(weatherCellStyle(reliable, weather.legend)).toMatchObject({ fillColor: '#2e7d32', fillOpacity: 0.45 })
})

test('approximate cells are filled with the hatch pattern of their risk', () => {
  expect(hatchId('High')).toBe('hatch-High')
  expect(weatherCellStyle(approximate, weather.legend)).toMatchObject({ fillColor: 'url(#hatch-High)' })
})

test('cells without enough data are grey', () => {
  expect(weatherCellStyle(insufficient, weather.legend)).toMatchObject({ fillColor: INSUFFICIENT_COLOR })
})

test('a risk missing from the legend is shown as grey, not as an invisible cell', () => {
  const odd = { properties: { display_risk: 'Extreme', display_style: 'solid' } }
  expect(weatherCellStyle(odd, weather.legend)).toMatchObject({ fillColor: INSUFFICIENT_COLOR })
})

test('popup shows the season and the backend message verbatim (HTML-escaped)', () => {
  const html = weatherPopupHtml({ season: 'S. Spring', message: 'APPROXIMATE: <x> & y' })
  expect(html).toContain('S. Spring')
  expect(html).toContain('APPROXIMATE: &lt;x&gt; &amp; y')
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/features/layers/WeatherLayer/weatherHelpers.test.js`
Expected: FAIL with `Failed to resolve import "./weatherHelpers.js"`.

- [ ] **Step 3: Implement `weatherHelpers.js`**

```js
import { escapeHtml } from '../../../utils/html.js'

export const INSUFFICIENT_COLOR = '#9e9e9e'

export const hatchId = (risk) => `hatch-${risk}`

// Data-sufficiency rule (SKILL.md §6): solid = reliable, hatched = approximate, grey = not enough data.
export function weatherCellStyle(feature, legend) {
  const { display_risk: risk, display_style: style } = feature.properties
  const color = legend[risk]
  if (style === 'grey' || !color) {
    return { color: '#757575', weight: 0.5, fillColor: INSUFFICIENT_COLOR, fillOpacity: 0.35 }
  }
  if (style === 'hatched') {
    return { color, weight: 0.5, fillColor: `url(#${hatchId(risk)})`, fillOpacity: 0.8 }
  }
  return { color, weight: 0.5, fillColor: color, fillOpacity: 0.45 }
}

// The message is rendered verbatim (only HTML-escaped), as the project rules require.
export function weatherPopupHtml(props) {
  return `<div class="popup"><strong>${escapeHtml(props.season)}</strong><p>${escapeHtml(props.message)}</p></div>`
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/features/layers/WeatherLayer/weatherHelpers.test.js`
Expected: PASS (5 tests).

- [ ] **Step 5: Write the failing component tests**

`src/features/layers/WeatherLayer/HatchPatterns.test.jsx`:

```jsx
import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import HatchPatterns from './HatchPatterns.jsx'

test('renders one SVG pattern per risk colour', () => {
  const { container } = render(<HatchPatterns colors={{ Low: '#2e7d32', High: '#c62828' }} />)
  expect(container.querySelectorAll('pattern')).toHaveLength(2)
  expect(container.querySelector('#hatch-High line')).toHaveAttribute('stroke', '#c62828')
})
```

`src/features/layers/WeatherLayer/WeatherLayer.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerFour } from '../../../test/fixtures.js'
import WeatherLayer from './WeatherLayer.jsx'

test('draws every grid cell of the season', () => {
  render(<WeatherLayer weather={layerFour('winter')} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('3')
})
```

- [ ] **Step 6: Run them to verify they fail**

Run: `npx vitest run src/features/layers/WeatherLayer`
Expected: the 2 new files FAIL with `Failed to resolve import "./HatchPatterns.jsx"` / `"./WeatherLayer.jsx"`.

- [ ] **Step 7: Implement `HatchPatterns.jsx`**

```jsx
import { hatchId } from './weatherHelpers.js'

// Hidden SVG with one diagonal-hatch <pattern> per risk colour; weather cells reference them by id.
export default function HatchPatterns({ colors }) {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        {Object.entries(colors).map(([risk, color]) => (
          <pattern
            key={risk}
            id={hatchId(risk)}
            width="8"
            height="8"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="8" height="8" fill={color} fillOpacity="0.25" />
            <line x1="0" y1="0" x2="0" y2="8" stroke={color} strokeWidth="3" />
          </pattern>
        ))}
      </defs>
    </svg>
  )
}
```

- [ ] **Step 8: Implement `WeatherLayer.jsx`**

```jsx
import { GeoJSON } from 'react-leaflet'
import { weatherCellStyle, weatherPopupHtml } from './weatherHelpers.js'

const onEachFeature = (feature, layer) => layer.bindPopup(weatherPopupHtml(feature.properties))

// Layer 4. `weather` is the /api/get-layer-four response for one season.
export default function WeatherLayer({ weather }) {
  return (
    <GeoJSON
      key={weather.season}
      data={weather}
      style={(feature) => weatherCellStyle(feature, weather.legend)}
      onEachFeature={onEachFeature}
    />
  )
}
```

- [ ] **Step 9: Run all weather tests to verify they pass**

Run: `npx vitest run src/features/layers/WeatherLayer`
Expected: PASS (7 tests).

- [ ] **Step 10: Commit**

```bash
git add src/features/layers/WeatherLayer
git commit -m "feat: add seasonal dust-storm risk layer with confidence hatching"
```

---

### Task 11: Panels: `LayerPanel`, `Legend`, `PointInfo`

**Files:**
- Create: `src/components/LayerPanel/LayerPanel.jsx`, `src/components/LayerPanel/LayerPanel.test.jsx`, `src/components/Legend/Legend.jsx`, `src/components/Legend/Legend.test.jsx`, `src/components/PointInfo/PointInfo.jsx`, `src/components/PointInfo/PointInfo.test.jsx`

- [ ] **Step 1: Write the failing `LayerPanel` test**

`src/components/LayerPanel/LayerPanel.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../../api/marsApi.js'
import { DEFAULT_VIEW, POI_CATEGORIES } from '../../config/layers.js'
import { layerOne, layerThree, layerTwo } from '../../test/fixtures.js'
import LayerPanel from './LayerPanel.jsx'

const ready = (data) => ({ status: 'ready', data, error: null })
const idle = { status: 'idle', data: null, error: null }

function renderPanel(view = {}, layers = {}) {
  const onChange = vi.fn()
  render(
    <LayerPanel
      view={{ ...DEFAULT_VIEW, ...view }}
      onChange={onChange}
      layers={{ baseImagery: ready(layerOne), relief: ready(layerTwo), pois: ready(layerThree), weather: idle, ...layers }}
    />,
  )
  return onChange
}

test('checks the backend default base source when none is chosen', () => {
  renderPanel()
  expect(screen.getByRole('radio', { name: /CTX mosaic, Coprates/ })).toBeChecked()
})

test('choosing another base source reports it', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('radio', { name: /HiRISE/ }))
  expect(onChange).toHaveBeenCalledWith({ baseSource: 'hirise' })
})

test('choosing a shaded relief source reports it, and Off reports null', () => {
  const onChange = renderPanel()
  const select = screen.getByRole('combobox', { name: /shaded relief/i })
  fireEvent.change(select, { target: { value: 'hillshade_color' } })
  expect(onChange).toHaveBeenLastCalledWith({ hillshadeSource: 'hillshade_color' })
  fireEvent.change(select, { target: { value: '' } })
  expect(onChange).toHaveBeenLastCalledWith({ hillshadeSource: null })
})

test('ticking walkability reports it', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('checkbox', { name: /walkability/i }))
  expect(onChange).toHaveBeenCalledWith({ walkability: true })
})

test('unticking a POI category removes it from the list', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('checkbox', { name: /^Minerals/ }))
  expect(onChange).toHaveBeenCalledWith({
    poiCategories: POI_CATEGORIES.map((c) => c.id).filter((id) => id !== 'mineral'),
  })
})

test('shows the feature count of each POI category', () => {
  renderPanel()
  expect(screen.getByRole('checkbox', { name: /^Exploration zones \(1\)/ })).toBeInTheDocument()
})

test('changing the season reports it', () => {
  const onChange = renderPanel({ weather: true })
  fireEvent.change(screen.getByRole('combobox', { name: /season/i }), { target: { value: 'winter' } })
  expect(onChange).toHaveBeenCalledWith({ season: 'winter' })
})

test('an unavailable layer shows the backend detail and the command that fixes it', () => {
  const error = new ApiError('Weather files not found', {
    status: 503,
    fix: 'python scripts/build_weather/build_weather.py',
  })
  renderPanel({ weather: true }, { weather: { status: 'error', data: null, error } })
  const alert = screen.getByRole('alert')
  expect(alert).toHaveTextContent('Weather files not found')
  expect(alert).toHaveTextContent('python scripts/build_weather/build_weather.py')
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/components/LayerPanel`
Expected: FAIL with `Failed to resolve import "./LayerPanel.jsx"`.

- [ ] **Step 3: Implement `LayerPanel.jsx`**

```jsx
import { POI_CATEGORIES, SEASONS } from '../../config/layers.js'

function LayerStatus({ layer }) {
  if (layer.status === 'loading' && !layer.data) return <p className="layer-status">Loading…</p>
  if (layer.status !== 'error') return null
  return (
    <div className="layer-status layer-status--error" role="alert">
      <p>{layer.error.message}</p>
      {layer.error.fix && (
        <p>
          To fix, run: <code>{layer.error.fix}</code>
        </p>
      )}
    </div>
  )
}

// Left-hand control panel. `layers` holds the useLayer state of each layer; `onChange` receives a partial view.
export default function LayerPanel({ view, onChange, layers }) {
  const { baseImagery, relief, pois, weather } = layers
  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source

  function toggleCategory(id) {
    const next = view.poiCategories.includes(id)
      ? view.poiCategories.filter((c) => c !== id)
      : [...view.poiCategories, id]
    onChange({ poiCategories: next })
  }

  return (
    <aside className="layer-panel" aria-label="Map layers">
      <header>
        <h1>Mars Map</h1>
        <p>East Melas / Coprates Chasma, Valles Marineris</p>
      </header>

      <section>
        <h2>Base map</h2>
        <LayerStatus layer={baseImagery} />
        {baseImagery.data?.sources.map((source) => (
          <label key={source.id} className="option">
            <input
              type="radio"
              name="base-source"
              value={source.id}
              checked={source.id === baseSourceId}
              onChange={() => onChange({ baseSource: source.id })}
            />
            <span>
              {source.title}
              <small>{source.coverage_note}</small>
            </span>
          </label>
        ))}
      </section>

      <section>
        <h2>Relief</h2>
        <LayerStatus layer={relief} />
        {relief.data && (
          <>
            <label className="option">
              Shaded relief
              <select
                value={view.hillshadeSource ?? ''}
                onChange={(e) => onChange({ hillshadeSource: e.target.value || null })}
              >
                <option value="">Off</option>
                {relief.data.hillshade_sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="option">
              <input
                type="checkbox"
                checked={view.walkability}
                onChange={(e) => onChange({ walkability: e.target.checked })}
              />
              Walkability (slope classes)
            </label>
          </>
        )}
      </section>

      <section>
        <h2>Points of interest</h2>
        <LayerStatus layer={pois} />
        {pois.data && (
          <>
            <label className="option">
              <input type="checkbox" checked={view.poi} onChange={(e) => onChange({ poi: e.target.checked })} />
              Show points of interest
            </label>
            <fieldset className="categories" disabled={!view.poi}>
              <legend className="visually-hidden">Categories</legend>
              {POI_CATEGORIES.map((c) => (
                <label key={c.id} className="option option--sub">
                  <input
                    type="checkbox"
                    checked={view.poiCategories.includes(c.id)}
                    onChange={() => toggleCategory(c.id)}
                  />
                  <span className="swatch swatch--round" style={{ background: c.color }} />
                  {c.label} ({pois.data.categories[c.id] ?? 0})
                </label>
              ))}
            </fieldset>
            <label className="option">
              <input
                type="checkbox"
                checked={view.sulfate}
                onChange={(e) => onChange({ sulfate: e.target.checked })}
              />
              Sulfate minerals (CRISM)
            </label>
          </>
        )}
      </section>

      <section>
        <h2>Dust-storm risk</h2>
        <label className="option">
          <input type="checkbox" checked={view.weather} onChange={(e) => onChange({ weather: e.target.checked })} />
          Show seasonal risk
        </label>
        <label className="option">
          Season
          <select value={view.season} disabled={!view.weather} onChange={(e) => onChange({ season: e.target.value })}>
            {SEASONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <LayerStatus layer={weather} />
      </section>
    </aside>
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/components/LayerPanel`
Expected: PASS (8 tests).

- [ ] **Step 5: Write the failing `Legend` test**

`src/components/Legend/Legend.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { DEFAULT_VIEW } from '../../config/layers.js'
import { layerFour, layerTwo } from '../../test/fixtures.js'
import Legend from './Legend.jsx'

const allOff = { ...DEFAULT_VIEW, poi: false, walkability: false, weather: false }

test('renders nothing when no layer with a legend is on', () => {
  const { container } = render(<Legend view={allOff} relief={layerTwo} weather={null} />)
  expect(container).toBeEmptyDOMElement()
})

test('lists slope classes and relief caveats when walkability is on', () => {
  render(<Legend view={{ ...allOff, walkability: true }} relief={layerTwo} weather={null} />)
  expect(screen.getByText('Easy walk')).toBeInTheDocument()
  expect(screen.getByText('Impassable')).toBeInTheDocument()
  expect(screen.getByText('The 200 m elevation grid underestimates local slope.')).toBeInTheDocument()
})

test('lists only the visible POI categories', () => {
  render(<Legend view={{ ...allOff, poi: true, poiCategories: ['dunes'] }} relief={null} weather={null} />)
  expect(screen.getByText('Dune fields')).toBeInTheDocument()
  expect(screen.queryByText('Minerals')).toBeNull()
})

test('weather legend shows risk levels, confidence styles, the demo-area message verbatim and the caveat', () => {
  const weather = layerFour('spring')
  render(<Legend view={{ ...allOff, weather: true }} relief={null} weather={weather} />)
  expect(screen.getByText('High')).toBeInTheDocument()
  expect(screen.getByText('Approximate (hatched)')).toBeInTheDocument()
  expect(screen.getByText('Not enough data')).toBeInTheDocument()
  expect(screen.getByText(weather.aoi_summary.message, { exact: false })).toBeInTheDocument()
  expect(screen.getByText(weather.caveat)).toBeInTheDocument()
})
```

- [ ] **Step 6: Run it to verify it fails**

Run: `npx vitest run src/components/Legend`
Expected: FAIL with `Failed to resolve import "./Legend.jsx"`.

- [ ] **Step 7: Implement `Legend.jsx`**

```jsx
import { POI_CATEGORIES } from '../../config/layers.js'
import { INSUFFICIENT_COLOR, hatchId } from '../../features/layers/WeatherLayer/weatherHelpers.js'

// `relief` = /api/get-layer-two response, `weather` = /api/get-layer-four response (or null when off/not loaded).
export default function Legend({ view, relief, weather }) {
  const showRelief = view.walkability && relief
  const showPoi = view.poi
  const showWeather = view.weather && weather
  if (!showRelief && !showPoi && !showWeather) return null

  return (
    <div className="legend" aria-label="Legend">
      {showRelief && (
        <section>
          <h3>Walkability (slope)</h3>
          <ul>
            {relief.slope_classes.map((c) => (
              <li key={c.id}>
                <span className="swatch" style={{ background: c.color }} />
                <span>{c.label}</span>
                <small>
                  {c.min_deg}–{c.max_deg}°
                </small>
              </li>
            ))}
          </ul>
          {relief.caveats.map((text) => (
            <p key={text} className="caveat">
              {text}
            </p>
          ))}
        </section>
      )}

      {showPoi && (
        <section>
          <h3>Points of interest</h3>
          <ul>
            {POI_CATEGORIES.filter((c) => view.poiCategories.includes(c.id)).map((c) => (
              <li key={c.id}>
                <span className="swatch swatch--round" style={{ background: c.color }} />
                <span>{c.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {showWeather && (
        <section>
          <h3>Dust-storm risk: {weather.season_name}</h3>
          <ul>
            {Object.entries(weather.legend).map(([risk, color]) => (
              <li key={risk}>
                <span className="swatch" style={{ background: color }} />
                <span>{risk}</span>
              </li>
            ))}
            <li>
              <svg className="swatch" viewBox="0 0 14 14" aria-hidden="true">
                <rect width="14" height="14" fill={`url(#${hatchId('Moderate')})`} />
              </svg>
              <span>Approximate (hatched)</span>
            </li>
            <li>
              <span className="swatch" style={{ background: INSUFFICIENT_COLOR }} />
              <span>Not enough data</span>
            </li>
          </ul>
          {weather.aoi_summary?.message && (
            <p className="weather-message">Demo area: {weather.aoi_summary.message}</p>
          )}
          <p className="caveat">{weather.caveat}</p>
        </section>
      )}
    </div>
  )
}
```

- [ ] **Step 8: Run it to verify it passes**

Run: `npx vitest run src/components/Legend`
Expected: PASS (4 tests).

- [ ] **Step 9: Write the failing `PointInfo` test**

`src/components/PointInfo/PointInfo.test.jsx`:

```jsx
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../../api/marsApi.js'
import { layerTwo, pointInfo } from '../../test/fixtures.js'
import PointInfo from './PointInfo.jsx'

const latlng = { lat: -12, lng: -70 }

test('renders nothing without a point', () => {
  const { container } = render(<PointInfo point={null} slopeClasses={[]} onClose={() => {}} />)
  expect(container).toBeEmptyDOMElement()
})

test('shows the coordinates while loading', () => {
  render(<PointInfo point={{ status: 'loading', latlng }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText('12.000° S, 70.000° W')).toBeInTheDocument()
  expect(screen.getByText('Loading…')).toBeInTheDocument()
})

test('shows elevation, slope, terrain class and the approximate label', () => {
  render(
    <PointInfo point={{ status: 'ready', latlng, data: pointInfo }} slopeClasses={layerTwo.slope_classes} onClose={() => {}} />,
  )
  expect(screen.getByText('-4,770.1 m')).toBeInTheDocument()
  expect(screen.getByText('1.96°')).toBeInTheDocument()
  expect(screen.getByText('Easy walk')).toBeInTheDocument()
  expect(screen.getByText(/approximate/i)).toBeInTheDocument()
})

test('says so when the point has no elevation data', () => {
  const data = { ...pointInfo, elevation_m: null, slope_deg: null, slope_class: null }
  render(<PointInfo point={{ status: 'ready', latlng, data }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText('No elevation data at this point.')).toBeInTheDocument()
})

test('shows the backend message for a point outside the demo area', () => {
  const error = new ApiError('Point is outside the area covered by the elevation data (East Melas demo area).', {
    status: 404,
  })
  render(<PointInfo point={{ status: 'error', latlng, error }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText(/outside the area covered/)).toBeInTheDocument()
})

test('close button calls onClose', () => {
  const onClose = vi.fn()
  render(<PointInfo point={{ status: 'loading', latlng }} slopeClasses={[]} onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'Close' }))
  expect(onClose).toHaveBeenCalled()
})
```

- [ ] **Step 10: Run it to verify it fails**

Run: `npx vitest run src/components/PointInfo`
Expected: FAIL with `Failed to resolve import "./PointInfo.jsx"`.

- [ ] **Step 11: Implement `PointInfo.jsx`**

```jsx
import { formatLatLng } from '../../config/map.js'

const yesNo = (value) => (value ? 'Yes' : 'No')

// "What's here?" card. `point` = { status: 'loading' | 'ready' | 'error', latlng, data?, error? }.
export default function PointInfo({ point, slopeClasses = [], onClose }) {
  if (!point) return null
  const { status, latlng, data, error } = point
  const slopeClass = data && slopeClasses.find((c) => c.id === data.slope_class)

  return (
    <div className="point-info" role="dialog" aria-label="Point details">
      <button type="button" className="point-info__close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      <h3>{formatLatLng(latlng.lat, latlng.lng)}</h3>
      {status === 'loading' && <p>Loading…</p>}
      {status === 'error' && <p className="point-info__error">{error.message}</p>}
      {status === 'ready' && data.elevation_m === null && <p>No elevation data at this point.</p>}
      {status === 'ready' && data.elevation_m !== null && (
        <>
          {data.approximate && <p className="badge">Approximate values (200 m elevation grid)</p>}
          <dl>
            <dt>Elevation</dt>
            <dd>{data.elevation_m.toLocaleString('en-US')} m</dd>
            <dt>Slope</dt>
            <dd>{data.slope_deg}°</dd>
            <dt>Terrain</dt>
            <dd>{slopeClass?.label ?? data.slope_class}</dd>
            <dt>On foot</dt>
            <dd>{yesNo(data.walkable)}</dd>
            <dt>By rover</dt>
            <dd>{yesNo(data.vehicle)}</dd>
          </dl>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 12: Run all panel tests to verify they pass**

Run: `npx vitest run src/components`
Expected: PASS (18 tests).

- [ ] **Step 13: Commit**

```bash
git add src/components
git commit -m "feat: add layer panel, legend and point info card"
```

---

### Task 12: Wire everything together in `App` + layout styles

**Files:**
- Modify: `src/App.jsx` (replace the placeholder entirely)
- Modify: `src/App.css` (fill in)
- Create: `src/App.test.jsx`

- [ ] **Step 1: Write the failing integration test**

`src/App.test.jsx`:

```jsx
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'
import { jsonResponse, layerFour, layerOne, layerThree, layerTwo, pointInfo, routeFetch } from './test/fixtures.js'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    routeFetch({
      '/api/get-layer-one': layerOne,
      '/api/get-layer-two/point': pointInfo,
      '/api/get-layer-two': layerTwo,
      '/api/get-layer-three': layerThree,
      '/api/get-layer-four': (path) =>
        jsonResponse(layerFour(new URL(path, 'http://localhost').searchParams.get('season'))),
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

const tileUrls = () => screen.getAllByTestId('tile-layer').map((t) => t.dataset.url)

test('loads the layers and shows the default base imagery and the POIs', async () => {
  render(<App />)
  expect(await screen.findByRole('radio', { name: /CTX mosaic, Coprates/ })).toBeChecked()
  expect(tileUrls()).toContain('/api/tiles/ctx_coprates/{z}/{y}/{x}')
  expect(await screen.findByTestId('geojson')).toHaveAttribute('data-count', '2')
})

test('switching the base map swaps the tile source', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('radio', { name: /HiRISE/ }))
  expect(tileUrls()).toContain('/api/tiles/hirise/{z}/{y}/{x}')
  expect(tileUrls()).not.toContain('/api/tiles/ctx_coprates/{z}/{y}/{x}')
})

test('turning on dust-storm risk loads the selected season and shows its message', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('checkbox', { name: /show seasonal risk/i }))
  expect(
    await screen.findByText(/APPROXIMATE: not enough data to reliably calculate the risk for the demo area/),
  ).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-four?season=spring')
})

test('clicking the map shows the point details', async () => {
  render(<App />)
  await screen.findByRole('radio', { name: /CTX mosaic, Coprates/ })
  act(() => mapEventHandlers.click({ latlng: { lat: -12, lng: -70 } }))
  expect(await screen.findByText('-4,770.1 m')).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-two/point?lon=-70&lat=-12')
})

test('shows a banner when the backend is down', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  render(<App />)
  await waitFor(() => expect(document.querySelector('.banner')).toHaveTextContent(/backend is not reachable/i))
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npx vitest run src/App.test.jsx`
Expected: FAIL. The placeholder renders no radio buttons (`Unable to find role="radio"`).

- [ ] **Step 3: Replace `src/App.jsx`**

```jsx
import { useCallback, useRef, useState } from 'react'
import { getBaseImagery, getPointInfo, getPois, getRelief, getWeather } from './api/marsApi.js'
import LayerPanel from './components/LayerPanel/LayerPanel.jsx'
import Legend from './components/Legend/Legend.jsx'
import PointInfo from './components/PointInfo/PointInfo.jsx'
import { DEFAULT_VIEW } from './config/layers.js'
import PoiLayer from './features/layers/PoiLayer/PoiLayer.jsx'
import ReliefLayer from './features/layers/ReliefLayer/ReliefLayer.jsx'
import TrekTileLayer from './features/layers/TrekTileLayer/TrekTileLayer.jsx'
import HatchPatterns from './features/layers/WeatherLayer/HatchPatterns.jsx'
import WeatherLayer from './features/layers/WeatherLayer/WeatherLayer.jsx'
import MarsMap from './features/map/MarsMap/MarsMap.jsx'
import { useLayer } from './hooks/useLayer.js'
import './App.css'

export default function App() {
  const [view, setView] = useState(DEFAULT_VIEW)
  const [point, setPoint] = useState(null)
  const pointRequest = useRef(0)

  const baseImagery = useLayer(getBaseImagery, [])
  const relief = useLayer(getRelief, [])
  const pois = useLayer(getPois, [])
  const weather = useLayer(() => getWeather(view.season), [view.season], view.weather)

  const updateView = useCallback((patch) => setView((prev) => ({ ...prev, ...patch })), [])

  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source
  const baseSource = baseImagery.data?.sources.find((s) => s.id === baseSourceId)
  const backendDown = [baseImagery, relief, pois].every((l) => l.status === 'error' && l.error.status === 0)

  async function showPoint(latlng) {
    const id = ++pointRequest.current // only the latest click may update the card
    setPoint({ status: 'loading', latlng })
    try {
      const data = await getPointInfo(latlng.lat, latlng.lng)
      if (id === pointRequest.current) setPoint({ status: 'ready', latlng, data })
    } catch (error) {
      if (id === pointRequest.current) setPoint({ status: 'error', latlng, error })
    }
  }

  function closePoint() {
    pointRequest.current += 1
    setPoint(null)
  }

  return (
    <div className="app">
      <MarsMap onMapClick={showPoint}>
        {baseSource && <TrekTileLayer source={baseSource} zIndex={1} />}
        {relief.data && (
          <ReliefLayer relief={relief.data} hillshadeSource={view.hillshadeSource} showWalkability={view.walkability} />
        )}
        {pois.data && (
          <PoiLayer
            pois={pois.data}
            categories={view.poiCategories}
            showMarkers={view.poi}
            showSulfate={view.sulfate}
          />
        )}
        {view.weather && weather.data && <WeatherLayer weather={weather.data} />}
      </MarsMap>

      {weather.data && <HatchPatterns colors={weather.data.legend} />}
      {backendDown && (
        <div className="banner" role="alert">
          {baseImagery.error.message}
        </div>
      )}

      <LayerPanel view={view} onChange={updateView} layers={{ baseImagery, relief, pois, weather }} />
      <Legend view={view} relief={relief.data} weather={view.weather ? weather.data : null} />
      <PointInfo point={point} slopeClasses={relief.data?.slope_classes} onClose={closePoint} />
    </div>
  )
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `npx vitest run src/App.test.jsx`
Expected: PASS (5 tests).

- [ ] **Step 5: Fill in `src/App.css`**

```css
.app {
  position: relative;
  height: 100%;
  overflow: hidden;
}

.leaflet-container.mars-map {
  position: absolute;
  inset: 0;
  background: #1a1411;
}

/* ---- left panel ---- */
.layer-panel {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 1000;
  width: 300px;
  max-height: calc(100% - 24px);
  overflow-y: auto;
  padding: 14px 16px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}

.layer-panel header h1 {
  margin: 0;
  font-size: 18px;
}

.layer-panel header p {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 12px;
}

.layer-panel section {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--panel-border);
}

.layer-panel h2 {
  margin: 0 0 6px;
  color: var(--muted);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.option {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  cursor: pointer;
}

.option input {
  accent-color: var(--accent);
}

.option small {
  display: block;
  color: var(--muted);
  font-size: 11px;
}

.option--sub {
  align-items: center;
  padding-left: 22px;
}

.option select {
  max-width: 165px;
  margin-left: auto;
  padding: 2px 4px;
  color: var(--text);
  background: #2a221e;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
}

.categories {
  margin: 0;
  padding: 0;
  border: 0;
}

.categories:disabled {
  opacity: 0.45;
}

.swatch {
  display: inline-block;
  flex: none;
  width: 14px;
  height: 14px;
  margin-right: 6px;
  border: 1px solid rgba(0, 0, 0, 0.4);
  border-radius: 3px;
}

.swatch--round {
  border-radius: 50%;
}

.layer-status {
  margin: 4px 0;
  color: var(--muted);
  font-size: 12px;
}

.layer-status p {
  margin: 2px 0;
}

.layer-status--error {
  color: #ffb4a2;
}

.layer-status code {
  color: var(--text);
  word-break: break-all;
}

/* ---- legend (bottom right, above the zoom buttons) ---- */
.legend {
  position: absolute;
  right: 12px;
  bottom: 96px;
  z-index: 1000;
  width: 280px;
  max-height: calc(100% - 120px);
  overflow-y: auto;
  padding: 8px 12px 10px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  font-size: 12px;
}

.legend h3 {
  margin: 6px 0;
  font-size: 12px;
}

.legend ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.legend li {
  display: flex;
  align-items: center;
  padding: 2px 0;
}

.legend li small {
  margin-left: auto;
  color: var(--muted);
}

.caveat {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 11px;
}

.weather-message {
  margin: 6px 0 0;
}

/* ---- point card (bottom centre) ---- */
.point-info {
  position: absolute;
  bottom: 24px;
  left: 50%;
  z-index: 1000;
  width: 300px;
  padding: 12px 16px;
  background: var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  transform: translateX(-50%);
}

.point-info h3 {
  margin: 0 24px 6px 0;
  font-size: 14px;
}

.point-info dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 12px;
  margin: 0;
}

.point-info dt {
  color: var(--muted);
}

.point-info dd {
  margin: 0;
}

.point-info__close {
  position: absolute;
  top: 6px;
  right: 8px;
  color: var(--muted);
  font-size: 18px;
  background: none;
  border: 0;
  cursor: pointer;
}

.point-info__error {
  color: #ffb4a2;
}

.badge {
  display: inline-block;
  margin: 0 0 6px;
  padding: 1px 6px;
  color: #1b1b1b;
  font-size: 11px;
  background: #f9a825;
  border-radius: 4px;
}

/* ---- misc ---- */
.coordinate-readout {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 1000;
  padding: 4px 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  background: var(--panel-bg);
  border-radius: 6px;
  pointer-events: none;
}

.banner {
  position: absolute;
  top: 12px;
  left: 50%;
  z-index: 1100;
  padding: 8px 14px;
  color: #fff;
  background: #7a2a1a;
  border-radius: 8px;
  transform: translateX(-50%);
}

.walkability-overlay {
  image-rendering: pixelated;
}

.leaflet-popup-content .popup p {
  margin: 6px 0;
}

.popup-meta {
  color: #666;
  font-size: 11px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 640px) {
  .layer-panel {
    width: calc(100% - 24px);
    max-height: 45%;
  }

  .legend,
  .coordinate-readout {
    display: none;
  }
}
```

- [ ] **Step 6: Run the full suite and the build**

```bash
npm test
```

Expected: 17 test files, 69 tests passed, 0 failed.

```bash
npm run build
```

Expected: `✓ built in …`.

- [ ] **Step 7: Commit**

```bash
git add src/App.jsx src/App.css src/App.test.jsx
git commit -m "feat: wire map, layers and panels into the app"
```

---

### Task 13: Check it in the browser, write the README

**Files:**
- Create: `.claude/launch.json`, `README.md`

- [ ] **Step 1: Add the dev-server preview config**

`.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "mars-web",
      "runtimeExecutable": "npm",
      "runtimeArgs": ["run", "dev"],
      "port": 5173
    }
  ]
}
```

- [ ] **Step 2: Start both servers**

The backend from Task 0 must still be running on :8000 (`curl -s localhost:8000/api/get-layer-one | head -c 50` returns JSON). Start the frontend with `npm run dev` (or the preview tool with `mars-web`) and open http://localhost:5173.

- [ ] **Step 3: Walk through this checklist and fix anything that fails**

1. CTX imagery of the canyon fills the centre of the screen at zoom 7. Tiles are not offset and show no grey squares (missing tiles stay transparent).
2. Switching to **HiRISE** and **CTX global** keeps the imagery in the same place. HiRISE shows scattered strips. A 512 px source drawn at the wrong position means `tileSize` is not 256 (see gotcha 2).
3. Zooming to 12 upscales the tiles; zooming out to 4 still shows them. The browser console shows no tile 404 storm outside the AOI, because the `bounds` option limits requests to the AOI.
4. **Shaded relief → MOLA + HRSC colour** draws coloured relief over the imagery. **Walkability** draws a pixelated green-to-red overlay exactly on the AOI.
5. POIs show as coloured circles and polygons. Clicking one opens a popup with name, category, description and source. Unticking a category hides those features. **Sulfate minerals (CRISM)** shows a coloured tile overlay.
6. **Show seasonal risk** draws the 1° grid. Spring has hatched cells (approximate). The legend shows the demo-area message verbatim and the caveat. Switching season redraws the grid. Clicking a cell opens a popup with the message.
7. Clicking anywhere in the AOI opens the point card with elevation, slope, terrain, foot/rover and the "Approximate values" badge. Clicking outside the AOI shows the backend's "outside the area" message.
8. The coordinate readout (top right) follows the cursor.
9. Stopping the backend and reloading shows the "backend is not reachable" banner.
10. At 375 px wide (phone), the panel fits the width and nothing scrolls horizontally.

- [ ] **Step 4: Write `README.md`**

````markdown
# Mars Map (web)

"Google Maps for Mars": a Leaflet map of the East Melas / Coprates Chasma demo area (Valles Marineris) with four layers:
base imagery, relief and walkability, points of interest, and seasonal dust-storm risk. Routing comes later.

The app reads all data from the team's FastAPI layer backend
(`NASA-space-apps-mars-map`, branch `feature/layer-ingestion`). It never calls NASA servers.

## Run

1. Backend (once: `git worktree add --detach ../mars-backend origin/feature/layer-ingestion` in the team repo):

   ```bash
   ./scripts/dev-backend.sh
   ```

   Override paths with `TEAM_REPO`, `BACKEND_DIR`, `MARS_DATA_DIR` if your folders differ.

2. Frontend:

   ```bash
   npm install
   npm run dev
   ```

   Open http://localhost:5173. Vite proxies `/api/*` to `localhost:8000`.

## Test

```bash
npm test
```

Tests run in jsdom with `react-leaflet` replaced by `src/test/reactLeafletMock.jsx` (see `vite.config.js`), because Leaflet
cannot draw vector layers without a real browser. Check map rendering itself in the browser.

## Notes

- The map uses `L.CRS.EPSG4326`: Mars Trek tiles are plain lat/lon, not Web Mercator.
- All Trek tiles are displayed at 256 px, even the 512 px HiRISE / CTX-global images.
- Slope and elevation values are approximate (200 m grid); dust-storm messages are shown verbatim from the backend.
````

- [ ] **Step 5: Final test run and commit**

```bash
npm test
```

Expected: all tests pass.

```bash
git add README.md .claude/launch.json
git commit -m "docs: add README and dev-server preview config"
```
