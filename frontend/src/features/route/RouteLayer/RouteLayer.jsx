import { CircleMarker, Pane, Polyline, Tooltip } from 'react-leaflet'

const latLng = ({ lon, lat }) => [lat, lon]

function routeLatLngs(route) {
  return route?.path?.coordinates?.map(([lon, lat]) => [lat, lon]) ?? []
}

function Stop({ point, label, color }) {
  if (!point) return null
  return (
    <CircleMarker center={latLng(point)} radius={6} pathOptions={{ color, fillColor: color, fillOpacity: 1 }}>
      <Tooltip direction="top">{label}</Tooltip>
    </CircleMarker>
  )
}

export default function RouteLayer({ route, draft }) {
  const path = routeLatLngs(route)
  return (
    <Pane name="planned-route" style={{ zIndex: 650 }}>
      {path.length > 1 && <Polyline positions={path} pathOptions={{ color: '#61dafb', weight: 5, opacity: 0.9 }} />}
      <Stop point={draft.start} label="Start" color="#5ce1a4" />
      {draft.destinations.map((point, index) => <Stop key={`${point.lon}-${point.lat}-${index}`} point={point} label={`Stop ${index + 1}`} color="#f6c453" />)}
      <Stop point={draft.end} label="Finish" color="#f38ba8" />
    </Pane>
  )
}
