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
