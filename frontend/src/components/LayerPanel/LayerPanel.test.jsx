import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../../api/marsApi.js'
import { DEFAULT_VIEW, POI_CATEGORIES } from '../../config/layers.js'
import { layerFour, layerOne, layerThree, layerTwo } from '../../test/fixtures.js'
import LayerPanel from './LayerPanel.jsx'

const ready = (data) => ({ status: 'ready', data, error: null })
const idle = { status: 'idle', data: null, error: null }

function renderPanel(view = {}, layers = {}) {
  const onChange = vi.fn()
  render(
    <LayerPanel
      view={{ ...DEFAULT_VIEW, ...view }}
      onChange={onChange}
      layers={{ baseImagery: ready(layerOne), relief: ready(layerTwo), pois: ready(layerThree), weather: idle, ...layers }}
    />,
  )
  return onChange
}

test('checks the backend default base source when none is chosen', () => {
  renderPanel()
  expect(screen.getByRole('radio', { name: /CTX mosaic, Coprates/ })).toBeChecked()
})

test('choosing another base source reports it', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('radio', { name: /HiRISE/ }))
  expect(onChange).toHaveBeenCalledWith({ baseSource: 'hirise' })
})

test('choosing a shaded relief source reports it, and Off reports null', () => {
  const onChange = renderPanel()
  const select = screen.getByRole('combobox', { name: /shaded relief/i })
  fireEvent.change(select, { target: { value: 'hillshade_color' } })
  expect(onChange).toHaveBeenLastCalledWith({ hillshadeSource: 'hillshade_color' })
  fireEvent.change(select, { target: { value: '' } })
  expect(onChange).toHaveBeenLastCalledWith({ hillshadeSource: null })
})

test('ticking walkability reports it', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('checkbox', { name: /walkability/i }))
  expect(onChange).toHaveBeenCalledWith({ walkability: true })
})

test('unticking a POI category removes it from the list', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('checkbox', { name: /^Minerals/ }))
  expect(onChange).toHaveBeenCalledWith({
    poiCategories: POI_CATEGORIES.map((c) => c.id).filter((id) => id !== 'mineral'),
  })
})

test('shows the feature count of each POI category', () => {
  renderPanel()
  expect(screen.getByRole('checkbox', { name: /^Exploration zones \(1\)/ })).toBeInTheDocument()
})

test('changing the season reports it', () => {
  const onChange = renderPanel({ weather: true })
  fireEvent.change(screen.getByRole('combobox', { name: /season/i }), { target: { value: 'winter' } })
  expect(onChange).toHaveBeenCalledWith({ season: 'winter' })
})

test('an unavailable layer shows the backend detail and the command that fixes it', () => {
  const error = new ApiError('Weather files not found', {
    status: 503,
    fix: 'python scripts/build_weather/build_weather.py',
  })
  renderPanel({ weather: true }, { weather: { status: 'error', data: null, error } })
  const alert = screen.getByRole('alert')
  expect(alert).toHaveTextContent('Weather files not found')
  expect(alert).toHaveTextContent('python scripts/build_weather/build_weather.py')
})

test('shows the data-sufficiency key and caveat with the weather layer', () => {
  renderPanel({ weather: true }, { weather: ready(layerFour('spring')) })
  expect(screen.getByText('Hatched = approximate · Grey = not enough data')).toBeInTheDocument()
  expect(screen.getByText('Values are historical frequencies, not forecasts.')).toHaveClass('caveat')
})

test('hides the weather caveat when the layer is off', () => {
  renderPanel({ weather: false }, { weather: ready(layerFour('spring')) })
  expect(screen.queryByText(/Hatched = approximate/)).not.toBeInTheDocument()
})

test('shows Updating… while reloading with data on screen', () => {
  renderPanel({ weather: true }, { weather: { status: 'loading', data: layerFour('spring'), error: null } })
  expect(screen.getByText('Updating…')).toHaveClass('layer-status')
})
