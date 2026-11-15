import { POI_CATEGORIES, SEASONS } from '../../config/layers.js'

function LayerStatus({ layer }) {
  if (layer.status === 'loading' && !layer.data) return <p className="layer-status">Loading…</p>
  if (layer.status === 'loading') return <p className="layer-status">Updating…</p>
  if (layer.status !== 'error') return null
  return (
    <div className="layer-status layer-status--error" role="alert">
      <p>{layer.error.message}</p>
      {layer.error.fix && (
        <p>
          To fix, run: <code>{layer.error.fix}</code>
        </p>
      )}
    </div>
  )
}

// Left-hand control panel. `layers` holds the useLayer state of each layer; `onChange` receives a partial view.
export default function LayerPanel({ view, onChange, layers }) {
  const { baseImagery, relief, pois, weather } = layers
  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source

  function toggleCategory(id) {
    const next = view.poiCategories.includes(id)
      ? view.poiCategories.filter((c) => c !== id)
      : [...view.poiCategories, id]
    onChange({ poiCategories: next })
  }

  return (
    <aside className="layer-panel" aria-label="Map layers">
      <header>
        <h1>Mars Map</h1>
        <p>East Melas / Coprates Chasma, Valles Marineris</p>
      </header>

      <section>
        <h2>Base map</h2>
        <LayerStatus layer={baseImagery} />
        {baseImagery.data?.sources.map((source) => (
          <label key={source.id} className="option">
            <input
              type="radio"
              name="base-source"
              value={source.id}
              checked={source.id === baseSourceId}
              onChange={() => onChange({ baseSource: source.id })}
            />
            <span>
              {source.title}
              <small>{source.coverage_note}</small>
            </span>
          </label>
        ))}
      </section>

      <section>
        <h2>Relief</h2>
        <LayerStatus layer={relief} />
        {relief.data && (
          <>
            <label className="option">
              Shaded relief
              <select
                value={view.hillshadeSource ?? ''}
                onChange={(e) => onChange({ hillshadeSource: e.target.value || null })}
              >
                <option value="">Off</option>
                {relief.data.hillshade_sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="option">
              <input
                type="checkbox"
                checked={view.walkability}
                onChange={(e) => onChange({ walkability: e.target.checked })}
              />
              Walkability (slope classes)
            </label>
          </>
        )}
      </section>

      <section>
        <h2>Points of interest</h2>
        <LayerStatus layer={pois} />
        {pois.data && (
          <>
            <label className="option">
              <input type="checkbox" checked={view.poi} onChange={(e) => onChange({ poi: e.target.checked })} />
              Show points of interest
            </label>
            <fieldset className="categories" disabled={!view.poi}>
              <legend className="visually-hidden">Categories</legend>
              {POI_CATEGORIES.map((c) => (
                <label key={c.id} className="option option--sub">
                  <input
                    type="checkbox"
                    checked={view.poiCategories.includes(c.id)}
                    onChange={() => toggleCategory(c.id)}
                  />
                  <span className="swatch swatch--round" style={{ background: c.color }} />
                  {c.label} ({pois.data.categories[c.id] ?? 0})
                </label>
              ))}
            </fieldset>
            <label className="option">
              <input
                type="checkbox"
                checked={view.sulfate}
                onChange={(e) => onChange({ sulfate: e.target.checked })}
              />
              Sulfate minerals (CRISM)
            </label>
          </>
        )}
      </section>

      <section>
        <h2>Dust-storm risk</h2>
        <label className="option">
          <input type="checkbox" checked={view.weather} onChange={(e) => onChange({ weather: e.target.checked })} />
          Show seasonal risk
        </label>
        <label className="option">
          Season
          <select value={view.season} disabled={!view.weather} onChange={(e) => onChange({ season: e.target.value })}>
            {SEASONS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <LayerStatus layer={weather} />
        {view.weather && weather.data && (
          <div className="weather-note">
            <p>Hatched = approximate · Grey = not enough data</p>
            <p className="caveat">{weather.data.caveat}</p>
          </div>
        )}
      </section>
    </aside>
  )
}
