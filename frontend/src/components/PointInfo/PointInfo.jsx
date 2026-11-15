import { formatLatLng } from '../../config/map.js'
import { categoryInfo } from '../../features/layers/PoiLayer/poiHelpers.js'

const yesNo = (value) => (value ? 'Yes' : 'No')

// "What's here?" card. `point` = { status: 'loading' | 'ready' | 'error', latlng, data?, error? }.
export default function PointInfo({ point, slopeClasses = [], areas = [], weather = null, onClose }) {
  if (!point) return null
  const { status, latlng, data, error } = point
  const slopeClass = data && slopeClasses.find((c) => c.id === data.slope_class)

  return (
    <div className="point-info" role="region" aria-label="Point details" aria-live="polite">
      <button type="button" className="point-info__close" aria-label="Close" onClick={onClose}>
        ×
      </button>
      <h3>{formatLatLng(latlng.lat, latlng.lng)}</h3>
      {status === 'loading' && <p>Loading…</p>}
      {status === 'error' && <p className="point-info__error">{error.message}</p>}
      {status === 'ready' && data.elevation_m === null && <p>No elevation data at this point.</p>}
      {status === 'ready' && data.elevation_m !== null && (
        <>
          {data.approximate && <p className="badge">Approximate values (200 m elevation grid)</p>}
          <dl>
            <dt>Elevation</dt>
            <dd>{data.elevation_m.toLocaleString('en-US')} m</dd>
            <dt>Slope</dt>
            <dd>{data.slope_deg}°</dd>
            <dt>Terrain</dt>
            <dd>{slopeClass?.label ?? data.slope_class}</dd>
            <dt>On foot</dt>
            <dd>{yesNo(data.walkable)}</dd>
            <dt>By rover</dt>
            <dd>{yesNo(data.vehicle)}</dd>
          </dl>
        </>
      )}
      {areas.length > 0 && (
        <section>
          <h4>Inside</h4>
          <ul>
            {areas.map((a, i) => (
              <li key={a.properties.id ?? i}>
                {a.properties.name} <span className="point-info__category">{categoryInfo(a.properties.category).label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {weather?.cell && (
        <section>
          <h4>Dust-storm risk — {weather.seasonName}</h4>
          <p>{weather.cell.properties.message}</p>
        </section>
      )}
    </div>
  )
}
