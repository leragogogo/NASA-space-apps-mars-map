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
