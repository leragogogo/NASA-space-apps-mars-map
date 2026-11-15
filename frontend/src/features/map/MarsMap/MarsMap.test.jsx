import { act, render, screen } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { expect, test, vi } from 'vitest'
import MarsMap from './MarsMap.jsx'

test('renders its children inside the map', () => {
  render(
    <MarsMap>
      <span>layer goes here</span>
    </MarsMap>,
  )
  expect(screen.getByTestId('map')).toContainElement(screen.getByText('layer goes here'))
})

test('forwards map clicks as lat/lng', () => {
  const onMapClick = vi.fn()
  render(<MarsMap onMapClick={onMapClick} />)
  act(() => mapEventHandlers.click({ latlng: { lat: -11.7, lng: -69.9 } }))
  expect(onMapClick).toHaveBeenCalledWith({ lat: -11.7, lng: -69.9 })
})
