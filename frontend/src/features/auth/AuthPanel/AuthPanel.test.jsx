import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import AuthPanel from './AuthPanel.jsx'

const props = { user: null, busy: false, onLogin: vi.fn(), onRegister: vi.fn(), onLogout: vi.fn() }

test('offers sign-in and registration without inventing account features', () => {
  render(<AuthPanel {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('Welcome back')
  fireEvent.click(screen.getByRole('tab', { name: 'Register' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('Body mass')
  expect(screen.getByRole('dialog')).toHaveTextContent('Birth year')
  expect(screen.queryByText(/forgot password/i)).not.toBeInTheDocument()
})

test('signed-in state shows the real user email and sign-out', () => {
  render(<AuthPanel {...props} user={{ email: 'pilot@example.com' }} />)
  expect(screen.getByText('pilot@example.com')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
  expect(props.onLogout).toHaveBeenCalled()
})
