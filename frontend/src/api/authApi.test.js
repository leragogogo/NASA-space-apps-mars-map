import { afterEach, expect, test, vi } from 'vitest'
import { getCurrentUser, login, register } from './authApi.js'
import { jsonResponse } from '../test/fixtures.js'

afterEach(() => vi.unstubAllGlobals())

test('login sends the OAuth2 form expected by FastAPI', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ access_token: 'token', token_type: 'bearer' }))
  vi.stubGlobal('fetch', fetchMock)
  await login('pilot@example.com', 'secret-pass')
  const [path, options] = fetchMock.mock.calls[0]
  expect(path).toBe('/api/auth/login')
  expect(options.method).toBe('POST')
  expect(options.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
  expect(options.body.toString()).toBe('username=pilot%40example.com&password=secret-pass')
})

test('registration sends only the approved account fields', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1 }, 201))
  vi.stubGlobal('fetch', fetchMock)
  const data = { email: 'pilot@example.com', password: 'secret-pass', body_mass_kg: 72, birth_year: 1992 }
  await register(data)
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(data)
})

test('current-user request uses bearer authentication', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 1, email: 'pilot@example.com' }))
  vi.stubGlobal('fetch', fetchMock)
  await getCurrentUser('jwt-value')
  expect(fetchMock).toHaveBeenCalledWith('/api/users/me', { headers: { Authorization: 'Bearer jwt-value' } })
})
