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
