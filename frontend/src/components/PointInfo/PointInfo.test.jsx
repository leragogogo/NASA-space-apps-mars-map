import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../../api/marsApi.js'
import { layerTwo, pointInfo } from '../../test/fixtures.js'
import PointInfo from './PointInfo.jsx'

const latlng = { lat: -12, lng: -70 }

test('renders nothing without a point', () => {
  const { container } = render(<PointInfo point={null} slopeClasses={[]} onClose={() => {}} />)
  expect(container).toBeEmptyDOMElement()
})

test('shows the coordinates while loading', () => {
  render(<PointInfo point={{ status: 'loading', latlng }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText('12.000° S, 70.000° W')).toBeInTheDocument()
  expect(screen.getByText('Loading…')).toBeInTheDocument()
})

test('shows elevation, slope, terrain class and the approximate label', () => {
  render(
    <PointInfo point={{ status: 'ready', latlng, data: pointInfo }} slopeClasses={layerTwo.slope_classes} onClose={() => {}} />,
  )
  expect(screen.getByText('-4,770.1 m')).toBeInTheDocument()
  expect(screen.getByText('1.96°')).toBeInTheDocument()
  expect(screen.getByText('Easy walk')).toBeInTheDocument()
  expect(screen.getByText(/approximate/i)).toBeInTheDocument()
})

test('says so when the point has no elevation data', () => {
  const data = { ...pointInfo, elevation_m: null, slope_deg: null, slope_class: null }
  render(<PointInfo point={{ status: 'ready', latlng, data }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText('No elevation data at this point.')).toBeInTheDocument()
})

test('shows the backend message for a point outside the demo area', () => {
  const error = new ApiError('Point is outside the area covered by the elevation data (East Melas demo area).', {
    status: 404,
  })
  render(<PointInfo point={{ status: 'error', latlng, error }} slopeClasses={[]} onClose={() => {}} />)
  expect(screen.getByText(/outside the area covered/)).toBeInTheDocument()
})

test('close button calls onClose', () => {
  const onClose = vi.fn()
  render(<PointInfo point={{ status: 'loading', latlng }} slopeClasses={[]} onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: 'Close' }))
  expect(onClose).toHaveBeenCalled()
})

const areas = [
  { properties: { name: 'Melas exploration zone boundary', category: 'exploration_zone' } },
  { properties: { name: 'Basalt unit', category: 'geology' } },
]
const weather = { seasonName: 'Southern Spring', cell: { properties: { message: 'APPROXIMATE: <b>not</b> enough & data' } } }

test('lists the areas containing the point with their category label', () => {
  render(<PointInfo point={{ status: 'loading', latlng }} areas={areas} onClose={() => {}} />)
  expect(screen.getByText('Inside')).toBeInTheDocument()
  expect(screen.getByText('Melas exploration zone boundary')).toBeInTheDocument()
  expect(screen.getByText('Exploration zones')).toBeInTheDocument()
  expect(screen.getByText('Basalt unit')).toBeInTheDocument()
})

test('shows the dust-storm message verbatim under a season heading', () => {
  render(<PointInfo point={{ status: 'loading', latlng }} weather={weather} onClose={() => {}} />)
  expect(screen.getByText('Dust-storm risk — Southern Spring')).toBeInTheDocument()
  expect(screen.getByText('APPROXIMATE: <b>not</b> enough & data')).toBeInTheDocument()
})

test('omits the sections when there is nothing at the point', () => {
  render(<PointInfo point={{ status: 'loading', latlng }} areas={[]} weather={null} onClose={() => {}} />)
  expect(screen.queryByText('Inside')).toBeNull()
  expect(screen.queryByText(/Dust-storm risk/)).toBeNull()
})

test('shows both sections even when the elevation request failed', () => {
  const error = new ApiError('Point is outside the area covered by the elevation data.', { status: 404 })
  render(<PointInfo point={{ status: 'error', latlng, error }} areas={areas} weather={weather} onClose={() => {}} />)
  expect(screen.getByText(/outside the area covered/)).toBeInTheDocument()
  expect(screen.getByText('Inside')).toBeInTheDocument()
  expect(screen.getByText(/Dust-storm risk/)).toBeInTheDocument()
})
