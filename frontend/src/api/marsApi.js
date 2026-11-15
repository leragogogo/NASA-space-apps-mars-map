// The only module that talks to the backend. Paths are relative; Vite proxies /api to :8000.

export class ApiError extends Error {
  constructor(message, { status = 0, fix = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fix = fix // shell command the backend suggests when a layer's data is missing (HTTP 503)
  }
}

const unreachable = () =>
  new ApiError('The backend is not reachable. Start it on port 8000 (scripts/dev-backend.sh).')

async function getJson(path) {
  let response
  try {
    response = await fetch(path)
  } catch {
    throw unreachable()
  }
  let body
  let parsed = true
  try {
    body = await response.json()
  } catch {
    parsed = false
    body = {}
  }
  if (!response.ok) {
    // Behind the Vite proxy a dead backend answers 502/504 with an empty text body instead of rejecting.
    // A real backend 5xx always carries a JSON body, so an unparsable one means nothing is listening.
    if (response.status >= 500 && !parsed) throw unreachable()
    const message = typeof body?.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new ApiError(message, { status: response.status, fix: body?.fix ?? null })
  }
  return body
}

export const getBaseImagery = () => getJson('/api/get-layer-one')

export const getRelief = () => getJson('/api/get-layer-two')

export const getPois = () => getJson('/api/get-layer-three')

export const getWeather = (season) => getJson(`/api/get-layer-four?${new URLSearchParams({ season })}`)

export const getPointInfo = (lat, lng) =>
  getJson(`/api/get-layer-two/point?${new URLSearchParams({ lon: String(lng), lat: String(lat) })}`)
