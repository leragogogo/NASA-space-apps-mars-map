import { render, screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { layerTwo } from '../../../test/fixtures.js'
import ReliefLayer from './ReliefLayer.jsx'

test('renders nothing when hillshade and walkability are off', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource={null} showWalkability={false} />)
  expect(screen.queryByTestId('tile-layer')).toBeNull()
  expect(screen.queryByTestId('image-overlay')).toBeNull()
})

test('renders the chosen hillshade source as semi-transparent tiles', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource="hillshade_color" showWalkability={false} />)
  const tile = screen.getByTestId('tile-layer')
  expect(tile.dataset.url).toBe('/api/tiles/hillshade_color/{z}/{y}/{x}')
  expect(tile.dataset.opacity).toBe('0.6')
})

test('renders the walkability PNG as an image overlay', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource={null} showWalkability />)
  expect(screen.getByTestId('image-overlay').dataset.url).toBe('/api/get-layer-two/walkability.png')
})

test('ignores an unknown hillshade id', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource="nope" showWalkability={false} />)
  expect(screen.queryByTestId('tile-layer')).toBeNull()
})

test('draws the walkability overlay inside its fixed pane', () => {
  render(<ReliefLayer relief={layerTwo} hillshadeSource={null} showWalkability />)
  expect(within(screen.getByTestId('pane-walkability')).getByTestId('image-overlay')).toBeInTheDocument()
})
