import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { DEFAULT_VIEW } from '../../config/layers.js'
import { layerFour, layerTwo } from '../../test/fixtures.js'
import Legend from './Legend.jsx'

const allOff = { ...DEFAULT_VIEW, poi: false, walkability: false, weather: false }

test('renders nothing when no layer with a legend is on', () => {
  const { container } = render(<Legend view={allOff} relief={layerTwo} weather={null} />)
  expect(container).toBeEmptyDOMElement()
})

test('lists slope classes and relief caveats when walkability is on', () => {
  render(<Legend view={{ ...allOff, walkability: true }} relief={layerTwo} weather={null} />)
  expect(screen.getByText('Easy walk')).toBeInTheDocument()
  expect(screen.getByText('Impassable')).toBeInTheDocument()
  expect(screen.getByText('The 200 m elevation grid underestimates local slope.')).toBeInTheDocument()
})

test('lists only the visible POI categories', () => {
  render(<Legend view={{ ...allOff, poi: true, poiCategories: ['dunes'] }} relief={null} weather={null} />)
  expect(screen.getByText('Dune fields')).toBeInTheDocument()
  expect(screen.queryByText('Minerals')).toBeNull()
})

test('weather legend shows risk levels, confidence styles, the demo-area message verbatim and the caveat', () => {
  const weather = layerFour('spring')
  render(<Legend view={{ ...allOff, weather: true }} relief={null} weather={weather} />)
  expect(screen.getByText('High')).toBeInTheDocument()
  expect(screen.getByText('Approximate (hatched)')).toBeInTheDocument()
  expect(screen.getByText('Not enough data')).toBeInTheDocument()
  expect(screen.getByText(weather.aoi_summary.message, { exact: false })).toBeInTheDocument()
  expect(screen.getByText(weather.caveat)).toBeInTheDocument()
})
