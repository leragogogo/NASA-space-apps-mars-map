import { act, render, screen } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { expect, test } from 'vitest'
import CoordinateReadout from './CoordinateReadout.jsx'

test('shows the cursor position and hides it when the cursor leaves the map', () => {
  render(<CoordinateReadout />)
  expect(screen.queryByText(/°/)).toBeNull()

  act(() => mapEventHandlers.mousemove({ latlng: { lat: -11.7, lng: -69.9 } }))
  expect(screen.getByText('11.700° S, 69.900° W')).toBeInTheDocument()

  act(() => mapEventHandlers.mouseout())
  expect(screen.queryByText(/°/)).toBeNull()
})
