import { useState } from 'react'

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

// Like the real lib: tileSize/maxNativeZoom are construction-only (frozen at mount); url/opacity/zIndex stay live.
export function TileLayer({ url, opacity = 1, tileSize, maxNativeZoom, zIndex }) {
  const [frozen] = useState({ tileSize, maxNativeZoom })
  return (
    <div
      data-testid="tile-layer"
      data-url={url}
      data-opacity={opacity}
      data-tile-size={frozen.tileSize}
      data-max-native-zoom={frozen.maxNativeZoom}
      data-z-index={zIndex}
    />
  )
}

export function ImageOverlay({ url, opacity = 1 }) {
  return <div data-testid="image-overlay" data-url={url} data-opacity={opacity} />
}

export function Pane({ name, children }) {
  return <div data-testid={`pane-${name}`}>{children}</div>
}

export function Polyline({ positions }) {
  return <div data-testid="polyline" data-positions={JSON.stringify(positions)} />
}

export function CircleMarker({ center, children }) {
  return <div data-testid="circle-marker" data-center={JSON.stringify(center)}>{children}</div>
}

export function Tooltip({ children }) {
  return <span>{children}</span>
}

// Like the real lib: `data` is read once at mount; `style` is re-applied on every render (setStyle).
export function GeoJSON({ data, style, interactive }) {
  const [frozen] = useState(data)
  const styles = frozen.features.map((f) => (style ? style(f) : null))
  return <div
      data-testid="geojson"
      data-count={frozen.features.length}
      data-styles={JSON.stringify(styles)}
      data-interactive={String(interactive ?? true)}
    />
}
