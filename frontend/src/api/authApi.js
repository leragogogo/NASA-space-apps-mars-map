import { requestJson } from './request.js'

const bearer = (token) => ({ Authorization: `Bearer ${token}` })

export const register = (data) =>
  requestJson('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })

export const login = (email, password) =>
  requestJson('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
  })

export const getCurrentUser = (token) =>
  requestJson('/api/users/me', { headers: bearer(token) })
