import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'
import { jsonResponse, layerFour, layerOne, layerThree, layerTwo, pointInfo, routeFetch } from './test/fixtures.js'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    routeFetch({
      '/api/get-layer-one': layerOne,
      '/api/get-layer-two/point': pointInfo,
      '/api/get-layer-two': layerTwo,
      '/api/get-layer-three': layerThree,
      '/api/get-layer-four': (path) =>
        jsonResponse(layerFour(new URL(path, 'http://localhost').searchParams.get('season'))),
    }),
  )
})

afterEach(() => vi.unstubAllGlobals())

const tileUrls = () => screen.getAllByTestId('tile-layer').map((t) => t.dataset.url)

test('loads the layers with the default base imagery and no points of interest until the user picks some', async () => {
  render(<App />)
  expect(await screen.findByRole('radio', { name: /CTX mosaic, Coprates/ })).toBeChecked()
  expect(tileUrls()).toContain('/api/tiles/ctx_coprates/{z}/{y}/{x}')
  expect(screen.queryByTestId('pane-poi-points')).not.toBeInTheDocument()
  fireEvent.click(await screen.findByRole('checkbox', { name: /^Minerals/ }))
  fireEvent.click(screen.getByRole('checkbox', { name: /^Exploration zones/ }))
  const points = await screen.findByTestId('pane-poi-points')
  expect(within(points).getByTestId('geojson')).toHaveAttribute('data-count', '1')
  const areas = await screen.findByTestId('pane-poi-areas')
  expect(within(areas).getByTestId('geojson')).toHaveAttribute('data-count', '1')
})

test('switching the base map swaps the tile source', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('radio', { name: /HiRISE/ }))
  expect(tileUrls()).toContain('/api/tiles/hirise/{z}/{y}/{x}')
  expect(tileUrls()).not.toContain('/api/tiles/ctx_coprates/{z}/{y}/{x}')
})

test('turning on dust-storm risk loads the selected season and shows its message', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('checkbox', { name: /show seasonal risk/i }))
  expect(
    await screen.findByText(/APPROXIMATE: not enough data to reliably calculate the risk for the demo area/),
  ).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-four?season=spring')
  const weatherPane = await screen.findByTestId('pane-weather')
  expect(within(weatherPane).getByTestId('geojson')).toHaveAttribute('data-count', '3')
})

test('turning dust-storm risk off removes the grid and hides its status', async () => {
  render(<App />)
  const toggle = await screen.findByRole('checkbox', { name: /show seasonal risk/i })
  fireEvent.click(toggle)
  await screen.findByTestId('pane-weather')
  fireEvent.click(toggle)
  expect(screen.queryByTestId('pane-weather')).not.toBeInTheDocument()
})

test('clicking the map shows the point details', async () => {
  render(<App />)
  await screen.findByRole('radio', { name: /CTX mosaic, Coprates/ })
  act(() => {
    mapEventHandlers.click({ latlng: { lat: -12, lng: -70 } })
  })
  expect(await screen.findByText('-4,770.1 m')).toBeInTheDocument()
  expect(fetch).toHaveBeenCalledWith('/api/get-layer-two/point?lon=-70&lat=-12')
})

test('shows a banner when the backend is down', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  render(<App />)
  await waitFor(() => expect(document.querySelector('.banner')).toHaveTextContent(/backend is not reachable/i))
})

test('shows a banner when the Vite proxy reports the backend is down', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError('Unexpected end of JSON input')
      },
    }),
  )
  render(<App />)
  await waitFor(() => expect(document.querySelector('.banner')).toHaveTextContent(/backend is not reachable/i))
})

const card = () => within(screen.getByRole('region', { name: 'Point details' }))

test('the point card shows the dust-storm message of the cell under the click', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('checkbox', { name: /show seasonal risk/i }))
  await screen.findByTestId('pane-weather')
  act(() => {
    mapEventHandlers.click({ latlng: { lat: -12.5, lng: -69.5 } })
  })
  expect(await card().findByText('APPROXIMATE: not enough data to reliably calculate the risk for this area.')).toBeInTheDocument()
  expect(card().getByText(/Dust-storm risk/)).toBeInTheDocument()
})

test('the point card lists the exploration zone containing the click', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('checkbox', { name: /^Exploration zones/ }))
  await screen.findByTestId('pane-poi-areas')
  act(() => {
    mapEventHandlers.click({ latlng: { lat: -10.5, lng: -69.7 } })
  })
  expect(await card().findByText('Melas exploration zone boundary')).toBeInTheDocument()
})

test('a window can be hidden on its own and brought back', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('button', { name: 'Hide layers' }))
  expect(screen.queryByRole('complementary', { name: 'Map layers' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Layers' }))
  expect(screen.getByRole('complementary', { name: 'Map layers' })).toBeInTheDocument()

  fireEvent.click(screen.getByRole('checkbox', { name: /^Minerals/ })) // something for the legend to show
  fireEvent.click(await screen.findByRole('button', { name: 'Hide legend' }))
  expect(screen.queryByRole('region', { name: 'Legend' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Legend' }))
  expect(screen.getByRole('region', { name: 'Legend' })).toBeInTheDocument()
})

test('Hide windows clears every panel off the map and Show windows brings them back', async () => {
  render(<App />)
  fireEvent.click(await screen.findByRole('checkbox', { name: /^Minerals/ }))
  await screen.findByRole('region', { name: 'Legend' })
  fireEvent.click(screen.getByRole('button', { name: 'Hide windows' }))
  expect(screen.queryByRole('complementary', { name: 'Map layers' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Legend' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Layers' })).not.toBeInTheDocument() // no restore buttons either
  expect(screen.getByTestId('pane-poi-points')).toBeInTheDocument() // the map layers stay
  fireEvent.click(screen.getByRole('button', { name: 'Show windows' }))
  expect(screen.getByRole('complementary', { name: 'Map layers' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Legend' })).toBeInTheDocument()
})
