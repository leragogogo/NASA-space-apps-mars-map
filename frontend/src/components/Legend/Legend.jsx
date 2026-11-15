import { POI_CATEGORIES } from '../../config/layers.js'
import { INSUFFICIENT_COLOR, hatchId } from '../../features/layers/WeatherLayer/weatherHelpers.js'

// `relief` = /api/get-layer-two response, `weather` = /api/get-layer-four response (or null when off/not loaded).
export default function Legend({ view, relief, weather }) {
  const showRelief = view.walkability && relief
  const showPoi = view.poi
  const showWeather = view.weather && weather
  if (!showRelief && !showPoi && !showWeather) return null

  return (
    <div className="legend" role="region" aria-label="Legend">
      {showRelief && (
        <section>
          <h3>Walkability (slope)</h3>
          <ul>
            {relief.slope_classes.map((c) => (
              <li key={c.id}>
                <span className="swatch" style={{ background: c.color }} />
                <span>{c.label}</span>
                <small>
                  {c.min_deg}–{c.max_deg}°
                </small>
              </li>
            ))}
          </ul>
          {relief.caveats.map((text) => (
            <p key={text} className="caveat">
              {text}
            </p>
          ))}
        </section>
      )}

      {showPoi && (
        <section>
          <h3>Points of interest</h3>
          <ul>
            {POI_CATEGORIES.filter((c) => view.poiCategories.includes(c.id)).map((c) => (
              <li key={c.id}>
                <span className="swatch swatch--round" style={{ background: c.color }} />
                <span>{c.label}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {showWeather && (
        <section>
          <h3>Dust-storm risk: {weather.season_name}</h3>
          <ul>
            {Object.entries(weather.legend).map(([risk, color]) => (
              <li key={risk}>
                <span className="swatch" style={{ background: color }} />
                <span>{risk}</span>
              </li>
            ))}
            <li>
              <svg className="swatch" viewBox="0 0 14 14" aria-hidden="true">
                <rect width="14" height="14" fill={`url(#${hatchId('Moderate')})`} />
              </svg>
              <span>Approximate (hatched)</span>
            </li>
            <li>
              <span className="swatch" style={{ background: INSUFFICIENT_COLOR }} />
              <span>Not enough data</span>
            </li>
          </ul>
          {weather.aoi_summary?.message && (
            <p className="weather-message">Demo area: {weather.aoi_summary.message}</p>
          )}
          <p className="caveat">{weather.caveat}</p>
        </section>
      )}
    </div>
  )
}
