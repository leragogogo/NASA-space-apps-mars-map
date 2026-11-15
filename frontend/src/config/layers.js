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
  // Points of interest start hidden: the user picks the categories they want to see.
  poi: false,
  poiCategories: [],
  sulfate: false,
  weather: false,
  season: 'spring',
}

// Custom Leaflet panes, so stacking never depends on toggle order (overlayPane is 400, markerPane 600).
export const PANES = {
  walkability: { name: 'walkability', zIndex: 405 },
  weather: { name: 'weather', zIndex: 410 },
  poiAreas: { name: 'poi-areas', zIndex: 420 },
  poiPoints: { name: 'poi-points', zIndex: 450 },
}
