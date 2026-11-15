import { requestJson } from './request.js'

export const calculateRoute = (request, token) =>
  requestJson('/api/route', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(request),
  })
