// Layer API. Paths are relative; Vite proxies /api to :8000.
import { requestJson } from './request.js'

export const getBaseImagery = () => requestJson('/api/get-layer-one')

export const getRelief = () => requestJson('/api/get-layer-two')

export const getPois = () => requestJson('/api/get-layer-three')

export const getWeather = (season) => requestJson(`/api/get-layer-four?${new URLSearchParams({ season })}`)

export const getPointInfo = (lat, lng) =>
  requestJson(`/api/get-layer-two/point?${new URLSearchParams({ lon: String(lng), lat: String(lat) })}`)

export { ApiError } from './request.js'
