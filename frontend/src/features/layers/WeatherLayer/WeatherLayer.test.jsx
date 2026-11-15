import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerFour } from '../../../test/fixtures.js'
import WeatherLayer from './WeatherLayer.jsx'

test('draws every grid cell of the season', () => {
  render(<WeatherLayer weather={layerFour('winter')} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('3')
})

test('is drawn inside the weather pane', () => {
  render(<WeatherLayer weather={layerFour('winter')} />)
  expect(within(screen.getByTestId('pane-weather')).getByTestId('geojson')).toBeInTheDocument()
})

test('rebuilds the layer when the season changes', () => {
  const spring = layerFour('spring')
  const winter = { ...layerFour('winter'), features: layerFour('winter').features.slice(0, 1) }
  const { rerender } = render(<WeatherLayer weather={spring} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('3')
  rerender(<WeatherLayer weather={winter} />)
  expect(screen.getByTestId('geojson').dataset.count).toBe('1')
})

test('the grid is click-through', () => {
  render(<WeatherLayer weather={layerFour('winter')} />)
  expect(screen.getByTestId('geojson').dataset.interactive).toBe('false')
})
