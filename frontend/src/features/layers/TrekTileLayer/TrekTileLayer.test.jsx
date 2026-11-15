import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerOne } from '../../../test/fixtures.js'
import TrekTileLayer from './TrekTileLayer.jsx'

const [ctxCoprates, ctxGlobal] = layerOne.sources

test('uses the source tile URL and native zoom range', () => {
  render(<TrekTileLayer source={ctxCoprates} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/ctx_coprates/{z}/{y}/{x}')
  expect(tile.dataset.maxNativeZoom).toBe('9')
  expect(tile.dataset.opacity).toBe('1')
})

test('always displays tiles at 256 px, even for 512 px sources', () => {
  render(<TrekTileLayer source={ctxGlobal} />)
  expect(screen.getByTestId('tile-layer').dataset.tileSize).toBe('256')
})

test('passes opacity and z-index through', () => {
  render(<TrekTileLayer source={ctxCoprates} opacity={0.6} zIndex={2} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.opacity).toBe('0.6')
  expect(tile.dataset.zIndex).toBe('2')
})

test('rebuilds the layer when the source changes (construction-only options)', () => {
  const { rerender } = render(<TrekTileLayer source={ctxCoprates} />)
  rerender(<TrekTileLayer source={{ ...ctxGlobal, max_zoom: 12 }} />)
  expect(screen.getByTestId('tile-layer').dataset.maxNativeZoom).toBe('12')
})
