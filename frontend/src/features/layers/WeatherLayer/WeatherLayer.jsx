import { useCallback } from 'react'
import { GeoJSON, Pane } from 'react-leaflet'
import { PANES } from '../../../config/layers.js'
import { weatherCellStyle } from './weatherHelpers.js'

// Layer 4. `weather` is the /api/get-layer-four response for one season.
export default function WeatherLayer({ weather }) {
  // Stable identity: react-leaflet calls setStyle on every cell whenever the style prop changes.
  const style = useCallback((feature) => weatherCellStyle(feature, weather.legend), [weather.legend])
  return (
    <Pane name={PANES.weather.name} style={{ zIndex: PANES.weather.zIndex }}>
      <GeoJSON key={weather.season} data={weather} style={style} interactive={false} />
    </Pane>
  )
}
