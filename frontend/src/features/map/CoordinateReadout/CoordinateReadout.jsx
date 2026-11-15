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
