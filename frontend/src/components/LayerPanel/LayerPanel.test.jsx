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

test('shows the product name exactly', () => {
  renderPanel()
  expect(screen.getByRole('heading', { level: 1, name: 'NASA Mars Map' })).toBeInTheDocument()
})

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

test('no points of interest are shown at the start', () => {
  renderPanel()
  expect(screen.getByRole('checkbox', { name: /All points of interest/ })).not.toBeChecked()
  for (const c of POI_CATEGORIES) {
    const box = screen.getByRole('checkbox', { name: new RegExp(`^${c.label}`) })
    expect(box).not.toBeChecked()
    expect(box).toBeEnabled() // the user can pick a category straight away
  }
})

test('ticking a category shows just that category', () => {
  const onChange = renderPanel()
  fireEvent.click(screen.getByRole('checkbox', { name: /^Dune fields/ }))
  expect(onChange).toHaveBeenCalledWith({ poi: true, poiCategories: ['dunes'] })
})

test('unticking a category removes it, and unticking the last one hides them all', () => {
  let onChange = renderPanel({ poi: true, poiCategories: ['mineral', 'dunes'] })
  fireEvent.click(screen.getByRole('checkbox', { name: /^Minerals/ }))
  expect(onChange).toHaveBeenCalledWith({ poi: true, poiCategories: ['dunes'] })
  document.body.innerHTML = ''
  onChange = renderPanel({ poi: true, poiCategories: ['dunes'] })
  fireEvent.click(screen.getByRole('checkbox', { name: /^Dune fields/ }))
  expect(onChange).toHaveBeenCalledWith({ poi: false, poiCategories: [] })
})

test('the All box works like select-all: on, partly on (a dash), off', () => {
  const all = POI_CATEGORIES.map((c) => c.id)
  const allBox = () => screen.getByRole('checkbox', { name: /All points of interest/ })
  let onChange = renderPanel()
  fireEvent.click(allBox())
  expect(onChange).toHaveBeenCalledWith({ poi: true, poiCategories: all })
  document.body.innerHTML = ''
  onChange = renderPanel({ poi: true, poiCategories: ['dunes'] })
  expect(allBox()).not.toBeChecked()
  expect(allBox().indeterminate).toBe(true)
  fireEvent.click(allBox()) // partly on -> all on
  expect(onChange).toHaveBeenCalledWith({ poi: true, poiCategories: all })
  document.body.innerHTML = ''
  onChange = renderPanel({ poi: true, poiCategories: all })
  expect(allBox()).toBeChecked()
  fireEvent.click(allBox())
  expect(onChange).toHaveBeenCalledWith({ poi: false, poiCategories: [] })
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

test('the weather caveat lives in the legend, not repeated in the panel', () => {
  renderPanel({ weather: true }, { weather: ready(layerFour('spring')) })
  expect(screen.queryByText(/Hatched = approximate/)).not.toBeInTheDocument()
  expect(screen.queryByText('Values are historical frequencies, not forecasts.')).not.toBeInTheDocument()
})

test('base map coverage notes are tooltips, not text', () => {
  renderPanel()
  const option = screen.getByRole('radio', { name: /CTX mosaic, Coprates/ }).closest('label')
  expect(option).toHaveAttribute('title')
  expect(option.textContent).not.toMatch(/coverage/)
  expect(option.getAttribute('title')).toMatch(/coverage/)
})

test('shows Updating… while reloading with data on screen', () => {
  renderPanel({ weather: true }, { weather: { status: 'loading', data: layerFour('spring'), error: null } })
  expect(screen.getByText('Updating…')).toHaveClass('layer-status')
})

test('the panel can be hidden', () => {
  const onHide = vi.fn()
  render(
    <LayerPanel view={DEFAULT_VIEW} onChange={vi.fn()} onHide={onHide}
      layers={{ baseImagery: ready(layerOne), relief: ready(layerTwo), pois: ready(layerThree), weather: idle }} />,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Hide layers' }))
  expect(onHide).toHaveBeenCalled()
})
