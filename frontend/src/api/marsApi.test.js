import { afterEach, expect, test, vi } from 'vitest'
import { jsonResponse, layerOne, pointInfo } from '../test/fixtures.js'
import { ApiError, getBaseImagery, getPointInfo, getPois, getRelief, getWeather } from './marsApi.js'

afterEach(() => vi.unstubAllGlobals())

function stubFetch(response) {
  const fetch = vi.fn(async () => response)
  vi.stubGlobal('fetch', fetch)
  return fetch
}

test('getBaseImagery returns layer one JSON', async () => {
  const fetch = stubFetch(jsonResponse(layerOne))
  await expect(getBaseImagery()).resolves.toEqual(layerOne)
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-one')
})

test('getRelief and getPois call layers two and three', async () => {
  const fetch = stubFetch(jsonResponse({}))
  await getRelief()
  await getPois()
  expect(fetch).toHaveBeenNthCalledWith(1, '/api/get-layer-two')
  expect(fetch).toHaveBeenNthCalledWith(2, '/api/get-layer-three')
})

test('getWeather sends the season as a query parameter', async () => {
  const fetch = stubFetch(jsonResponse({}))
  await getWeather('winter')
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-four?season=winter')
})

test('getPointInfo sends lon and lat', async () => {
  const fetch = stubFetch(jsonResponse(pointInfo))
  await expect(getPointInfo(-11.7, -69.9)).resolves.toEqual(pointInfo)
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-two/point?lon=-69.9&lat=-11.7')
})

test('a 503 becomes an ApiError with the backend detail and fix', async () => {
  stubFetch(jsonResponse({ detail: 'Weather files not found', fix: 'python scripts/build_weather/build_weather.py' }, 503))
  const error = await getWeather('spring').catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.message).toBe('Weather files not found')
  expect(error.status).toBe(503)
  expect(error.fix).toBe('python scripts/build_weather/build_weather.py')
})

test('a non-string detail (FastAPI validation error) falls back to a generic message', async () => {
  stubFetch(jsonResponse({ detail: [{ msg: 'field required' }] }, 422))
  const error = await getWeather('x').catch((e) => e)
  expect(error.message).toBe('Request failed (422)')
  expect(error.fix).toBeNull()
})

test('a network failure becomes an ApiError with status 0', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  const error = await getBaseImagery().catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(0)
  expect(error.message).toMatch(/backend is not reachable/i)
})

test('a 502 from the Vite proxy with a non-JSON body is treated as the backend being unreachable', async () => {
  stubFetch({ ok: false, status: 502, json: () => Promise.reject(new SyntaxError('Unexpected end of JSON input')) })
  const error = await getBaseImagery().catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.status).toBe(0)
  expect(error.message).toMatch(/backend is not reachable/i)
})

test('a null JSON body still produces an ApiError', async () => {
  stubFetch(jsonResponse(null, 500))
  const error = await getBaseImagery().catch((e) => e)
  expect(error).toBeInstanceOf(ApiError)
  expect(error.message).toBe('Request failed (500)')
  expect(error.status).toBe(500)
  expect(error.fix).toBeNull()
})
