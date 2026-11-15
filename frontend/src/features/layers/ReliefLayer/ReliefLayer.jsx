import { ImageOverlay, Pane } from 'react-leaflet'
import { LAYER_OPACITY, PANES } from '../../../config/layers.js'
import TrekTileLayer from '../TrekTileLayer/TrekTileLayer.jsx'

// Layer 2. `relief` is the /api/get-layer-two response.
export default function ReliefLayer({ relief, hillshadeSource, showWalkability }) {
  const hillshade = relief.hillshade_sources.find((s) => s.id === hillshadeSource)
  return (
    <>
      {hillshade && <TrekTileLayer source={hillshade} opacity={LAYER_OPACITY.hillshade} zIndex={2} />}
      {showWalkability && (
        <Pane name={PANES.walkability.name} style={{ zIndex: PANES.walkability.zIndex }}>
          <ImageOverlay
            url={relief.overlay.url}
            bounds={relief.overlay.bounds}
            opacity={LAYER_OPACITY.walkability}
            className="walkability-overlay"
          />
        </Pane>
      )}
    </>
  )
}
