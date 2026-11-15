import { afterEach, expect, test, vi } from 'vitest'
import { calculateRoute } from './routeApi.js'
import { jsonResponse } from '../test/fixtures.js'

afterEach(() => vi.unstubAllGlobals())

test('route request preserves profile, multiple destinations, season and mode', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ path: { coordinates: [] } }))
  vi.stubGlobal('fetch', fetchMock)
  const request = {
    profile: 'car',
    start: { lon: -70, lat: -12 },
    destinations: [{ lon: -69.9, lat: -12.1 }, { lon: -69.8, lat: -12.2 }],
    end_mode: 'open',
    season: 'spring',
  }
  await calculateRoute(request, 'jwt-value')
  const [path, options] = fetchMock.mock.calls[0]
  expect(path).toBe('/api/route')
  expect(options.headers.Authorization).toBe('Bearer jwt-value')
  expect(JSON.parse(options.body)).toEqual(request)
})
