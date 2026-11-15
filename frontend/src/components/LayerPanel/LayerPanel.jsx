import { useEffect, useRef } from 'react'
import { POI_CATEGORIES, SEASONS } from '../../config/layers.js'
import { HideIcon } from '../Icons/icons.jsx'

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
export default function LayerPanel({ view, onChange, layers, onHide }) {
  const { baseImagery, relief, pois, weather } = layers
  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source

  // Categories are opt-in: ticking one shows it (and turns points of interest on), unticking the last hides them.
  const shown = view.poi ? view.poiCategories : []
  const allShown = shown.length === POI_CATEGORIES.length
  const allBox = useRef(null)
  useEffect(() => {
    // Some but not all categories on: the All box shows a dash, like a select-all checkbox.
    if (allBox.current) allBox.current.indeterminate = shown.length > 0 && !allShown
  })

  function toggleCategory(id) {
    const next = shown.includes(id) ? shown.filter((c) => c !== id) : [...shown, id]
    onChange({ poi: next.length > 0, poiCategories: next })
  }

  function toggleAll(on) {
    onChange(on ? { poi: true, poiCategories: POI_CATEGORIES.map((c) => c.id) } : { poi: false, poiCategories: [] })
  }

  return (
    <aside className="layer-panel" aria-label="Map layers">
      <header className="panel-head">
        <div>
          <h1>NASA Mars Map</h1>
          <p>East Melas / Coprates Chasma, Valles Marineris</p>
        </div>
        {onHide && (
          <button type="button" className="icon-button" aria-label="Hide layers" title="Hide layers" onClick={onHide}>
            <HideIcon />
          </button>
        )}
      </header>

      <section>
        <h2>Base map</h2>
        <LayerStatus layer={baseImagery} />
        {baseImagery.data?.sources.map((source) => (
          <label key={source.id} className="option" title={source.coverage_note}>
            <input
              type="radio"
              name="base-source"
              value={source.id}
              checked={source.id === baseSourceId}
              onChange={() => onChange({ baseSource: source.id })}
            />
            <span>{source.title}</span>
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
              Walkability (slope)
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
              <input ref={allBox} type="checkbox" checked={allShown} onChange={() => toggleAll(!allShown)} />
              All points of interest
            </label>
            <fieldset className="categories">
              <legend className="visually-hidden">Categories</legend>
              {POI_CATEGORIES.map((c) => (
                <label key={c.id} className="option option--sub">
                  <input
                    type="checkbox"
                    checked={shown.includes(c.id)}
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
      </section>
    </aside>
  )
}
