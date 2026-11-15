import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { jsonResponse } from '../../../test/fixtures.js'
import RoutePlanner from './RoutePlanner.jsx'
import { formatDuration, grams, wattHours } from './format.js'

afterEach(() => vi.unstubAllGlobals())

const start = { lon: -70, lat: -12 }
const stops = [{ lon: -69.5, lat: -11.5 }, { lon: -69.1, lat: -11.2 }]

const props = (overrides = {}) => ({
  token: 'jwt', draft: { start, destinations: [stops[0]], end: null },
  setDraft: vi.fn(), pickTarget: null, setPickTarget: vi.fn(), season: 'spring', route: null, onRouteChange: vi.fn(),
  ...overrides,
})

const getRoute = () => screen.getByRole('button', { name: 'Get route' })

test('asks the backend to choose the travel mode by default and sends the login token', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ stop_order: [0], resources: {} }))
  vi.stubGlobal('fetch', fetchMock)
  const p = props()
  render(<RoutePlanner {...p} />)
  expect(screen.getByRole('radio', { name: 'Best' })).toHaveAttribute('aria-checked', 'true')
  fireEvent.click(getRoute())
  await waitFor(() => expect(p.onRouteChange).toHaveBeenCalledTimes(2))
  const [path, options] = fetchMock.mock.calls[0]
  expect(path).toBe('/api/route')
  expect(options.headers.Authorization).toBe('Bearer jwt')
  expect(JSON.parse(options.body)).toMatchObject({ profile: 'auto', end_mode: 'round_trip', destinations: [stops[0]] })
  expect(p.setPickTarget).toHaveBeenCalledWith(null) // map clicks stop adding points
})

test('the travel mode chips pick walking or the rover', async () => {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ stop_order: [0], resources: {} }))
  vi.stubGlobal('fetch', fetchMock)
  render(<RoutePlanner {...props()} />)
  fireEvent.click(screen.getByRole('radio', { name: 'Walk' }))
  fireEvent.click(getRoute())
  await waitFor(() => expect(fetchMock).toHaveBeenCalled())
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).profile).toBe('astronaut')
})

test('lists the stops as numbered waypoints in the order they were added', () => {
  render(<RoutePlanner {...props({ draft: { start, destinations: stops, end: null } })} />)
  expect(screen.getByText('Stop 1').nextSibling).toHaveTextContent('-11.500, -69.500')
  expect(screen.getByText('Stop 2').nextSibling).toHaveTextContent('-11.200, -69.100')
})

test('a stop can be removed', () => {
  const p = props({ draft: { start, destinations: stops, end: null } })
  render(<RoutePlanner {...p} />)
  fireEvent.click(screen.getByRole('button', { name: 'Remove stop 1' }))
  const update = p.setDraft.mock.calls[0][0]
  expect(update({ start, destinations: stops, end: null }).destinations).toEqual([stops[1]])
})

test('clicking a waypoint or Add stop starts placing it on the map', () => {
  const p = props()
  render(<RoutePlanner {...p} />)
  fireEvent.click(screen.getByRole('button', { name: /Start/ }))
  expect(p.setPickTarget).toHaveBeenLastCalledWith('start')
  fireEvent.click(screen.getByRole('button', { name: 'Add stop' }))
  expect(p.setPickTarget).toHaveBeenLastCalledWith('destination')
})

test('a chosen finish is needed in Set finish mode and is enough without stops', () => {
  const { rerender } = render(<RoutePlanner {...props()} />)
  fireEvent.click(screen.getByRole('radio', { name: 'Set finish' }))
  expect(screen.getByRole('button', { name: /Finish/ })).toBeInTheDocument()
  expect(getRoute()).toBeDisabled() // no finish yet
  rerender(<RoutePlanner {...props({ draft: { start, destinations: [], end: { lon: -69, lat: -11 } } })} />)
  expect(getRoute()).toBeEnabled()
})

test('the result leads with the travel time and tucks the details away', () => {
  const route = {
    profile: 'car', stop_order: [0, 1], total_weight: 12345.67, dropped: [], body_mass_kg: null,
    resources: { time_s: 77940, o2_g: 1512.4, water_g: 5457.1, energy_wh: 143546.6, co2_g: 1808.6 },
    warnings: ['APPROXIMATE: not enough data to reliably calculate the risk.'],
    mode: {
      requested: 'auto', chosen: 'car', reason: 'Chose the vehicle: it uses less oxygen per person.',
      options: [
        { profile: 'astronaut', feasible: false, reached: 0, o2_g: null, time_s: null, reason: 'too steep' },
        { profile: 'car', feasible: true, reached: 2, o2_g: 756, time_s: 77940, reason: null },
      ],
    },
  }
  render(<RoutePlanner {...props({ route })} />)
  expect(screen.getByText('21 h 39 min')).toBeInTheDocument()
  expect(screen.getByText('2 stops in your order')).toBeInTheDocument()
  expect(screen.getByText('1.5 kg')).toBeInTheDocument()
  expect(screen.getByText('143.5 kWh')).toBeInTheDocument()
  expect(screen.queryByText(/12,345/)).not.toBeInTheDocument() // the internal planning cost stays hidden
  expect(screen.getByText('Why rover?')).toBeInTheDocument()
  expect(screen.getByText('Chose the vehicle: it uses less oxygen per person.')).toBeInTheDocument()
  expect(screen.getByText('Walk: too steep')).toBeInTheDocument()
  expect(screen.getByText('1 warning')).toBeInTheDocument()
  expect(screen.getByText('APPROXIMATE: not enough data to reliably calculate the risk.')).toBeInTheDocument()
})

test('skipped stops are named', () => {
  const route = { profile: 'astronaut', stop_order: [1], resources: { time_s: 600 }, warnings: [],
    dropped: [{ index: 0, point: stops[0], reason: 'unreachable_for_profile' }] }
  render(<RoutePlanner {...props({ route })} />)
  expect(screen.getByText('Stop 1 skipped: not reachable this way.')).toBeInTheDocument()
})

test('the planner collapses to its travel mode bar', () => {
  render(<RoutePlanner {...props()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse route planner' }))
  expect(screen.queryByRole('button', { name: 'Get route' })).not.toBeInTheDocument()
  expect(screen.getByRole('radio', { name: 'Best' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Expand route planner' }))
  expect(getRoute()).toBeInTheDocument()
})

test('durations read like a map app', () => {
  expect(formatDuration(45 * 60)).toBe('45 min')
  expect(formatDuration(2 * 3600)).toBe('2 h')
  expect(formatDuration(77940)).toBe('21 h 39 min')
  expect([grams(850), grams(1512.4), wattHours(900), wattHours(143546.6)]).toEqual(['850 g', '1.5 kg', '900 Wh', '143.5 kWh'])
})
