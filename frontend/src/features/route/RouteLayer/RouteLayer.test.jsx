import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import RouteLayer from './RouteLayer.jsx'

test('converts GeoJSON longitude-latitude into Leaflet latitude-longitude', () => {
  const route = { path: { coordinates: [[-70, -12], [-69.5, -11.5]] } }
  const draft = { start: { lon: -70, lat: -12 }, destinations: [{ lon: -69.5, lat: -11.5 }], end: null }
  render(<RouteLayer route={route} draft={draft} />)
  expect(screen.getByTestId('polyline').dataset.positions).toBe('[[-12,-70],[-11.5,-69.5]]')
  expect(screen.getAllByTestId('circle-marker')).toHaveLength(2)
})
