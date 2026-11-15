import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { mapEventHandlers } from 'react-leaflet'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
  for (const key of Object.keys(mapEventHandlers)) delete mapEventHandlers[key]
})
