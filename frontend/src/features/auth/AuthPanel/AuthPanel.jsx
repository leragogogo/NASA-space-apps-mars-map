import { useState } from 'react'

const initialForm = { email: '', password: '', body_mass_kg: '75', birth_year: '1990' }
const currentYear = new Date().getFullYear()

export default function AuthPanel({ user, busy, onLogin, onRegister, onLogout }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState(initialForm)
  const [error, setError] = useState('')

  if (user) {
    return (
      <div className="auth-toolbar" aria-label="Account controls">
        <span title={user.email}>{user.email}</span>
        <button type="button" onClick={onLogout}>Sign out</button>
      </div>
    )
  }

  async function submit(event) {
    event.preventDefault()
    setError('')
    try {
      if (mode === 'login') await onLogin(form.email, form.password)
      else {
        await onRegister({
          email: form.email,
          password: form.password,
          body_mass_kg: Number(form.body_mass_kg),
          birth_year: Number(form.birth_year),
        })
      }
      setOpen(false)
      setForm(initialForm)
    } catch (caught) {
      setError(caught.message)
    }
  }

  return (
    <>
      <button className="auth-open" type="button" onClick={() => setOpen(true)}>Sign in</button>
      {open && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setOpen(false)}>
          <section className="auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title" onMouseDown={(e) => e.stopPropagation()}>
            <button className="modal-close" type="button" aria-label="Close" onClick={() => setOpen(false)}>&times;</button>
            <p className="eyebrow">NASA Mars Map</p>
            <h2 id="auth-title">{mode === 'login' ? 'Welcome back' : 'Create your account'}</h2>
            <div className="auth-tabs" role="tablist" aria-label="Account action">
              <button type="button" role="tab" aria-selected={mode === 'login'} onClick={() => { setMode('login'); setError('') }}>Sign in</button>
              <button type="button" role="tab" aria-selected={mode === 'register'} onClick={() => { setMode('register'); setError('') }}>Register</button>
            </div>
            <form onSubmit={submit}>
              <label>Email<input name="email" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
              <label>Password<input name="password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required minLength="8" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
              {mode === 'register' && (
                <div className="auth-row">
                  <label>Body mass (kg)<input name="body_mass_kg" type="number" min="30" max="250" step="0.1" required value={form.body_mass_kg} onChange={(e) => setForm({ ...form, body_mass_kg: e.target.value })} /></label>
                  <label>Birth year<input name="birth_year" type="number" min="1900" max={currentYear} required value={form.birth_year} onChange={(e) => setForm({ ...form, birth_year: e.target.value })} /></label>
                </div>
              )}
              {error && <p className="form-error" role="alert">{error}</p>}
              <button className="primary-button" type="submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}</button>
            </form>
            <p className="auth-note">Estimates only, not operational guidance.</p>
          </section>
        </div>
      )}
    </>
  )
}
