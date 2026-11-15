import { useCallback, useMemo, useRef, useState } from 'react'
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
import { useLayer } from './hooks/useLayer.js'
import { featuresAt } from './utils/geo.js'
import './App.css'

export default function App() {
  const [view, setView] = useState(DEFAULT_VIEW)
  const [point, setPoint] = useState(null)
  const pointRequest = useRef(0)

  const baseImagery = useLayer(getBaseImagery, [])
  const relief = useLayer(getRelief, [])
  const pois = useLayer(getPois, [])
  const weather = useLayer(() => getWeather(view.season), [view.season], view.weather)

  const updateView = useCallback((patch) => setView((prev) => ({ ...prev, ...patch })), [])

  const baseSourceId = view.baseSource ?? baseImagery.data?.default_source
  const baseSource = baseImagery.data?.sources.find((s) => s.id === baseSourceId)
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

  return (
    <div className="app">
      <MarsMap onMapClick={showPoint}>
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
      </MarsMap>

      {weather.data && <HatchPatterns colors={weather.data.legend} />}
      {backendDown && (
        <div className="banner" role="alert">
          {baseImagery.error.message}
        </div>
      )}

      <LayerPanel view={view} onChange={updateView} layers={{ baseImagery, relief, pois, weather }} />
      <Legend view={view} relief={relief.data} weather={view.weather ? weather.data : null} />
      <PointInfo
        point={point}
        slopeClasses={relief.data?.slope_classes}
        areas={areas}
        weather={weatherCell ? { seasonName: weather.data.season_name, cell: weatherCell } : null}
        onClose={closePoint}
      />
    </div>
  )
}
