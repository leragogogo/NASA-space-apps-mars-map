import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { POI_CATEGORIES } from '../../../config/layers.js'
import { layerThree } from '../../../test/fixtures.js'
import PoiLayer from './PoiLayer.jsx'

const ALL = POI_CATEGORIES.map((c) => c.id)

const areasPane = () => screen.getByTestId('pane-poi-areas')
const pointsPane = () => screen.getByTestId('pane-poi-points')
const layerIn = (pane) => within(pane).getByTestId('geojson')

test('splits features into an areas layer and a points layer, each in its own pane', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers showSulfate={false} />)
  expect(layerIn(areasPane()).dataset.count).toBe('1')
  expect(layerIn(pointsPane()).dataset.count).toBe('1')
})

test('points keep the marker style and areas the path style', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers showSulfate={false} />)
  const [pointStyle] = JSON.parse(layerIn(pointsPane()).dataset.styles)
  const [areaStyle] = JSON.parse(layerIn(areasPane()).dataset.styles)
  expect(pointStyle.fillOpacity).toBe(0.95)
  expect(areaStyle.fillOpacity).toBe(0.06)
})

test('shows only the chosen categories', () => {
  render(<PoiLayer pois={layerThree} categories={['mineral']} showMarkers showSulfate={false} />)
  expect(layerIn(areasPane()).dataset.count).toBe('0')
  expect(layerIn(pointsPane()).dataset.count).toBe('1')
})

test('rebuilds the layers when the category list changes', () => {
  const { rerender } = render(<PoiLayer pois={layerThree} categories={ALL} showMarkers showSulfate={false} />)
  rerender(<PoiLayer pois={layerThree} categories={['exploration_zone']} showMarkers showSulfate={false} />)
  expect(layerIn(areasPane()).dataset.count).toBe('1')
  expect(layerIn(pointsPane()).dataset.count).toBe('0')
})

test('hides the features when markers are off', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers={false} showSulfate={false} />)
  expect(screen.queryByTestId('geojson')).toBeNull()
  expect(screen.queryByTestId('pane-poi-points')).toBeNull()
})

test('shows the CRISM sulfate tiles when asked', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers={false} showSulfate />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/crism_sulfate/{z}/{y}/{x}')
  expect(tile.dataset.opacity).toBe('0.7')
})

test('areas are click-through; points stay clickable', () => {
  render(<PoiLayer pois={layerThree} categories={ALL} showMarkers showSulfate={false} />)
  expect(layerIn(areasPane()).dataset.interactive).toBe('false')
  expect(layerIn(pointsPane()).dataset.interactive).toBe('true')
})
