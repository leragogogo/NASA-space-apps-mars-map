import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getCurrentUser, login, register } from './api/authApi.js'
import { getBaseImagery, getPointInfo, getPois, getRelief, getWeather } from './api/marsApi.js'
import LayerPanel from './components/LayerPanel/LayerPanel.jsx'
import Legend from './components/Legend/Legend.jsx'
import PointInfo from './components/PointInfo/PointInfo.jsx'
import { DEFAULT_VIEW } from './config/layers.js'
import PoiLayer from './features/layers/PoiLayer/PoiLayer.jsx'
import { splitPois } from './features/layers/PoiLayer/poiHelpers.js'
import ReliefLayer from './features/layers/ReliefLayer/ReliefLayer.jsx'
import TrekTileLayer from './features/layers/TrekTileLayer/TrekTileLayer.jsx'
import HatchPatterns from './features/layers/WeatherLayer/HatchPatterns.jsx'
import WeatherLayer from './features/layers/WeatherLayer/WeatherLayer.jsx'
import MarsMap from './features/map/MarsMap/MarsMap.jsx'
import { EyeIcon, LayersIcon } from './components/Icons/icons.jsx'
import AuthPanel from './features/auth/AuthPanel/AuthPanel.jsx'
import RouteLayer from './features/route/RouteLayer/RouteLayer.jsx'
import RoutePlanner from './features/route/RoutePlanner/RoutePlanner.jsx'
import { useLayer } from './hooks/useLayer.js'
import { featuresAt } from './utils/geo.js'
import './App.css'

export default function App() {
  const [view, setView] = useState(DEFAULT_VIEW)
  // Which floating windows are open. `all: false` clears every window off the map (the map layers stay).
  const [windows, setWindows] = useState({ all: true, layers: true, legend: true })
  const showWindows = (patch) => setWindows((current) => ({ ...current, ...patch }))
  const [point, setPoint] = useState(null)
  const pointRequest = useRef(0)
  const hostname = window.location.hostname
  const secureAccess = window.isSecureContext || hostname === 'localhost' || hostname === '127.0.0.1'
  const [auth, setAuth] = useState(() => {
    if (!secureAccess) return { status: 'insecure', token: null, user: null }
    const token = sessionStorage.getItem('mars-map-token')
    return token ? { status: 'loading', token, user: null } : { status: 'anonymous', token: null, user: null }
  })
  const [routeDraft, setRouteDraft] = useState({ start: null, destinations: [], end: null })
  const [pickTarget, setPickTarget] = useState(null)
  const [route, setRoute] = useState(null)

  useEffect(() => {
    if (auth.status !== 'loading' || !auth.token) return
    getCurrentUser(auth.token)
      .then((user) => setAuth({ status: 'ready', token: auth.token, user }))
      .catch(() => {
        sessionStorage.removeItem('mars-map-token')
        setAuth({ status: 'anonymous', token: null, user: null })
      })
  }, [auth.status, auth.token])

  const baseImagery = useLayer(getBaseImagery, [])
  const relief = useLayer(getRelief, [])
  const pois = useLayer(getPois, [])
  const weather = useLayer(() => getWeather(view.season), [view.season], view.weather)

  const updateView = useCallback((patch) => setView((prev) => ({ ...prev, ...patch })), [])

  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source
  const baseSource = baseImagery.data?.sources.find((s) => s.id === baseSourceId)
  const hasLegend = (view.walkability && relief.data) || view.poi || (view.weather && weather.data)
  const backendDown = [baseImagery, relief, pois].every((l) => l.status === 'error' && l.error.status === 0)

  const latlng = point?.latlng
  const areas = useMemo(() => {
    if (!latlng || !view.poi || !pois.data) return []
    return featuresAt(splitPois(pois.data, view.poiCategories).areas.features, latlng.lng, latlng.lat)
  }, [latlng, view.poi, view.poiCategories, pois.data])
  const weatherCell = useMemo(() => {
    if (!latlng || !view.weather || !weather.data) return null
    return featuresAt(weather.data.features, latlng.lng, latlng.lat)[0] ?? null
  }, [latlng, view.weather, weather.data])

  async function showPoint(latlng) {
    const id = ++pointRequest.current // only the latest click may update the card
    setPoint({ status: 'loading', latlng })
    try {
      const data = await getPointInfo(latlng.lat, latlng.lng)
      if (id === pointRequest.current) setPoint({ status: 'ready', latlng, data })
    } catch (error) {
      if (id === pointRequest.current) setPoint({ status: 'error', latlng, error })
    }
  }

  function closePoint() {
    pointRequest.current += 1
    setPoint(null)
  }

  function handleMapClick(latlng) {
    if (!pickTarget) {
      showPoint(latlng)
      return
    }
    const selected = { lon: latlng.lng, lat: latlng.lat }
    setRouteDraft((current) => {
      if (pickTarget === 'destination') return { ...current, destinations: [...current.destinations, selected] }
      return { ...current, [pickTarget]: selected }
    })
    setRoute(null)
    if (pickTarget !== 'destination') setPickTarget(null)
  }

  async function signIn(email, password) {
    setAuth((current) => ({ ...current, status: 'busy' }))
    try {
      const result = await login(email, password)
      const user = await getCurrentUser(result.access_token)
      sessionStorage.setItem('mars-map-token', result.access_token)
      setAuth({ status: 'ready', token: result.access_token, user })
    } catch (error) {
      setAuth({ status: 'anonymous', token: null, user: null })
      throw error
    }
  }

  async function createAccount(data) {
    setAuth((current) => ({ ...current, status: 'busy' }))
    try {
      await register(data)
      await signIn(data.email, data.password)
    } catch (error) {
      setAuth({ status: 'anonymous', token: null, user: null })
      throw error
    }
  }

  function signOut() {
    sessionStorage.removeItem('mars-map-token')
    setAuth({ status: 'anonymous', token: null, user: null })
    setRoute(null)
    setPickTarget(null)
  }

  return (
    <div className="app">
      <MarsMap onMapClick={handleMapClick}>
        {baseSource && <TrekTileLayer source={baseSource} zIndex={1} />}
        {relief.data && (
          <ReliefLayer relief={relief.data} hillshadeSource={view.hillshadeSource} showWalkability={view.walkability} />
        )}
        {pois.data && (
          <PoiLayer
            pois={pois.data}
            categories={view.poiCategories}
            showMarkers={view.poi}
            showSulfate={view.sulfate}
          />
        )}
        {view.weather && weather.data && <WeatherLayer weather={weather.data} />}
        {auth.user && <RouteLayer route={route} draft={routeDraft} />}
      </MarsMap>

      {weather.data && <HatchPatterns colors={weather.data.legend} />}
      {backendDown && (
        <div className="banner" role="alert">
          {baseImagery.error.message}
        </div>
      )}

      {windows.all && (windows.layers ? (
        <LayerPanel view={view} onChange={updateView} layers={{ baseImagery, relief, pois, weather }}
          onHide={() => showWindows({ layers: false })} />
      ) : (
        <button type="button" className="panel-pill panel-pill--layers" onClick={() => showWindows({ layers: true })}>
          <LayersIcon /> Layers
        </button>
      ))}
      <button type="button" className="panel-pill windows-toggle" aria-pressed={!windows.all}
        onClick={() => showWindows({ all: !windows.all })}>
        <EyeIcon off={windows.all} /> {windows.all ? 'Hide windows' : 'Show windows'}
      </button>
      {windows.all && <PointInfo
        point={point}
        slopeClasses={relief.data?.slope_classes}
        areas={areas}
        weather={weatherCell ? { seasonName: weather.data.season_name, cell: weatherCell } : null}
        onClose={closePoint}
      />}
      {/* One right-hand column: account, route planner (scrolls) and legend never overlap. */}
      <div className="right-rail">
        {secureAccess ? (
          <AuthPanel user={auth.user} busy={auth.status === 'busy'} onLogin={signIn} onRegister={createAccount} onLogout={signOut} />
        ) : (
          <div className="secure-notice" role="status">Sign-in needs HTTPS.</div>
        )}
        {windows.all && auth.user && (
          <RoutePlanner
            token={auth.token}
            draft={routeDraft}
            setDraft={setRouteDraft}
            pickTarget={pickTarget}
            setPickTarget={setPickTarget}
            season={view.season}
            route={route}
            onRouteChange={setRoute}
          />
        )}
        {windows.all && (windows.legend ? (
          <Legend view={view} relief={relief.data} weather={view.weather ? weather.data : null}
            onHide={() => showWindows({ legend: false })} />
        ) : hasLegend && (
          <button type="button" className="panel-pill legend-pill" onClick={() => showWindows({ legend: true })}>Legend</button>
        ))}
      </div>
    </div>
  )
}
