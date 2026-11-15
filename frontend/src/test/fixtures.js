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
