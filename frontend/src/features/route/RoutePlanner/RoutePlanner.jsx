import { useEffect, useRef, useState } from 'react'
import { calculateRoute } from '../../../api/routeApi.js'
import { coordinate, formatDuration, grams, kilograms, wattHours } from './format.js'
import { BestIcon, ChevronIcon, CloseIcon, PlusIcon, RoverIcon, WalkIcon } from '../../../components/Icons/icons.jsx'

const MODES = [
  { id: 'auto', label: 'Best', Icon: BestIcon },
  { id: 'astronaut', label: 'Walk', Icon: WalkIcon },
  { id: 'car', label: 'Rover', Icon: RoverIcon },
]
const PROFILE = { astronaut: { label: 'Walk', Icon: WalkIcon }, car: { label: 'Rover', Icon: RoverIcon } }
const FINISHES = [
  { id: 'round_trip', label: 'Round trip' },
  { id: 'open', label: 'One way' },
  { id: 'fixed', label: 'Set finish' },
]

function ResourceChips({ resources }) {
  const chips = [
    ['Oxygen', resources.o2_g, grams],
    ['Water', resources.water_g, grams],
    ['Energy', resources.energy_wh, wattHours],
    ['CO₂', resources.co2_g, grams],
  ].filter(([, value]) => value != null)
  return (
    <dl className="resource-chips">
      {chips.map(([label, value, format]) => (
        <div key={label}><dt>{label}</dt><dd>{format(value)}</dd></div>
      ))}
    </dl>
  )
}

// One row of the Google-Maps-style stop list: a marker, the place, and optional actions.
function Waypoint({ kind, marker, label, point, active, onPick, onRemove }) {
  return (
    <li className={`waypoint waypoint--${kind}${active ? ' is-active' : ''}`}>
      <span className="waypoint__marker" aria-hidden="true">{marker}</span>
      <button type="button" className="waypoint__place" aria-pressed={onPick ? active : undefined}
        onClick={onPick} disabled={!onPick}>
        <span className="waypoint__label">{label}</span>
        <span className="waypoint__value">{point ? coordinate(point) : 'Click to choose on map'}</span>
      </button>
      {onRemove && (
        <button type="button" className="icon-button" aria-label={`Remove ${label.toLowerCase()}`} onClick={onRemove}>
          <CloseIcon />
        </button>
      )}
    </li>
  )
}

function RouteResult({ route }) {
  const ref = useRef(null)
  // Bring the new result into view inside the scrolling panel.
  useEffect(() => {
    ref.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [route])
  const chosen = PROFILE[route.mode?.chosen ?? route.profile]
  const rejected = route.mode?.options.filter((option) => !option.feasible) ?? []
  const stops = route.stop_order.length
  return (
    <div className="route-result" aria-live="polite" ref={ref}>
      <div className="route-summary">
        <span className="route-time">{formatDuration(route.resources.time_s ?? 0)}</span>
        {chosen && <span className="route-mode-tag"><chosen.Icon /> {chosen.label}</span>}
      </div>
      <p className="route-sub">{stops ? `${stops} stop${stops === 1 ? '' : 's'} in your order` : 'Direct route'}</p>
      <ResourceChips resources={route.resources} />
      {route.dropped?.map((stop) => (
        <p className="route-warning" key={stop.index}>Stop {stop.index + 1} skipped: not reachable this way.</p>
      ))}
      {route.mode?.requested === 'auto' && (
        <details className="route-details">
          <summary>Why {chosen?.label.toLowerCase()}?</summary>
          <p>{route.mode.reason}</p>
          {rejected.map((option) => (
            <p key={option.profile}>{PROFILE[option.profile]?.label ?? option.profile}: {option.reason}</p>
          ))}
        </details>
      )}
      {route.warnings?.length > 0 && (
        <details className="route-details route-details--warn">
          <summary>{route.warnings.length} warning{route.warnings.length === 1 ? '' : 's'}</summary>
          {route.warnings.map((warning) => <p key={warning}>{warning}</p>)}
        </details>
      )}
      {route.body_mass_kg && <p className="route-caveat">Estimates for {kilograms(route.body_mass_kg)} kg body mass</p>}
    </div>
  )
}

export default function RoutePlanner({ token, draft, setDraft, pickTarget, setPickTarget, season, route, onRouteChange }) {
  const [profile, setProfile] = useState('auto')
  const [endMode, setEndMode] = useState('round_trip')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(false)

  // A fixed finish needs no destinations (a direct start -> finish route); the other modes need at least one.
  const ready = Boolean(draft.start) && (endMode === 'fixed' ? Boolean(draft.end) : draft.destinations.length > 0)

  async function calculate() {
    setPickTarget(null) // map clicks stop adding points once the route is requested
    setStatus('loading')
    setError('')
    onRouteChange(null)
    try {
      const request = { profile, start: draft.start, destinations: draft.destinations, end_mode: endMode, season }
      if (endMode === 'fixed') request.end = draft.end
      onRouteChange(await calculateRoute(request, token))
      setStatus('ready')
    } catch (caught) {
      setError(caught.message)
      setStatus('error')
    }
  }

  function removeStop(index) {
    setDraft((current) => ({ ...current, destinations: current.destinations.filter((_, i) => i !== index) }))
    onRouteChange(null)
  }

  function reset() {
    setDraft({ start: null, destinations: [], end: null })
    setPickTarget(null)
    onRouteChange(null)
    setStatus('idle')
    setError('')
  }

  const pick = (target) => setPickTarget(pickTarget === target ? null : target)

  return (
    <section className={`route-panel${collapsed ? ' is-collapsed' : ''}`} aria-label="Route planner">
      <header className="route-head">
        <div className="mode-chips" role="radiogroup" aria-label="Travel mode">
          {MODES.map(({ id, label, Icon }) => (
            <button key={id} type="button" role="radio" aria-checked={profile === id} onClick={() => setProfile(id)}>
              <Icon /><span>{label}</span>
            </button>
          ))}
        </div>
        <button type="button" className="icon-button" aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand route planner' : 'Collapse route planner'} onClick={() => setCollapsed(!collapsed)}>
          <ChevronIcon up={!collapsed} />
        </button>
      </header>

      {!collapsed && (
        <div className="route-body">
          <ol className="waypoints">
            <Waypoint kind="start" marker="" label="Start" point={draft.start}
              active={pickTarget === 'start'} onPick={() => pick('start')} />
            {draft.destinations.map((point, index) => (
              <Waypoint key={`${point.lon}-${point.lat}-${index}`} kind="stop" marker={index + 1}
                label={`Stop ${index + 1}`} point={point} onRemove={() => removeStop(index)} />
            ))}
            {endMode === 'fixed' && (
              <Waypoint kind="finish" marker="" label="Finish" point={draft.end}
                active={pickTarget === 'end'} onPick={() => pick('end')} />
            )}
            <li className="waypoint waypoint--add">
              <span className="waypoint__marker" aria-hidden="true"><PlusIcon /></span>
              <button type="button" className="waypoint__place" aria-pressed={pickTarget === 'destination'}
                onClick={() => pick('destination')}>
                <span className="waypoint__label">Add stop</span>
              </button>
            </li>
          </ol>

          <div className="segmented" role="radiogroup" aria-label="Route finish">
            {FINISHES.map(({ id, label }) => (
              <button key={id} type="button" role="radio" aria-checked={endMode === id}
                onClick={() => { setEndMode(id); setPickTarget(null) }}>{label}</button>
            ))}
          </div>

          {pickTarget && (
            <p className="pick-hint" role="status">
              Click the map to place {pickTarget === 'destination' ? 'a stop' : `the ${pickTarget === 'end' ? 'finish' : 'start'}`}
            </p>
          )}

          <div className="route-buttons">
            <button className="primary-button" type="button" disabled={!ready || status === 'loading'} onClick={calculate}>
              {status === 'loading' ? 'Finding route…' : 'Get route'}
            </button>
            <button type="button" className="text-button" onClick={reset}>Clear</button>
          </div>
          {error && <p className="form-error" role="alert">{error}</p>}
          {route && <RouteResult route={route} />}
        </div>
      )}
    </section>
  )
}
