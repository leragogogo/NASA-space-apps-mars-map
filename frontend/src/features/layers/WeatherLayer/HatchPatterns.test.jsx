import { render } from '@testing-library/react'
import { expect, test } from 'vitest'
import HatchPatterns from './HatchPatterns.jsx'

test('renders one SVG pattern per risk colour', () => {
  const { container } = render(<HatchPatterns colors={{ Low: '#2e7d32', High: '#c62828' }} />)
  expect(container.querySelectorAll('pattern')).toHaveLength(2)
  expect(container.querySelector('#hatch-High line')).toHaveAttribute('stroke', '#c62828')
})
