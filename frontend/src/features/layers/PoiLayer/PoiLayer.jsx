import { useMemo } from 'react'
import { GeoJSON, Pane } from 'react-leaflet'
import { LAYER_OPACITY, PANES, SULFATE_SOURCE_ID } from '../../../config/layers.js'
import TrekTileLayer from '../TrekTileLayer/TrekTileLayer.jsx'
import { poiMarkerStyle, poiPathStyle, poiPointToLayer, poiPopupHtml, splitPois } from './poiHelpers.js'

const onEachFeature = (feature, layer) => layer.bindPopup(poiPopupHtml(feature.properties))

// Layer 3. `pois` is the /api/get-layer-three response.
export default function PoiLayer({ pois, categories, showMarkers, showSulfate }) {
  const { areas, points } = useMemo(() => splitPois(pois, categories), [pois, categories])
  const sulfate = pois.overlays.find((o) => o.id === SULFATE_SOURCE_ID)
  // react-leaflet's GeoJSON ignores new `data` after mount; the key forces a rebuild when the filter changes.
  const key = categories.join(',')
  return (
    <>
      {showSulfate && sulfate && <TrekTileLayer source={sulfate} opacity={LAYER_OPACITY.sulfate} zIndex={3} />}
      {showMarkers && (
        <>
          <Pane name={PANES.poiAreas.name} style={{ zIndex: PANES.poiAreas.zIndex }}>
            <GeoJSON key={key} data={areas} style={poiPathStyle} interactive={false} />
          </Pane>
          <Pane name={PANES.poiPoints.name} style={{ zIndex: PANES.poiPoints.zIndex }}>
            <GeoJSON
              key={key}
              data={points}
              style={poiMarkerStyle}
              pointToLayer={poiPointToLayer}
              onEachFeature={onEachFeature}
            />
          </Pane>
        </>
      )}
    </>
  )
}
