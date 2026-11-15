export class ApiError extends Error {
  constructor(message, { status = 0, fix = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.fix = fix
  }
}

const unreachable = () =>
  new ApiError('The backend is not reachable. Start it on port 8000 (scripts/dev-backend.sh).')

export async function requestJson(path, options) {
  let response
  try {
    response = options ? await fetch(path, options) : await fetch(path)
  } catch {
    throw unreachable()
  }

  let body
  let parsed = true
  try {
    body = await response.json()
  } catch {
    parsed = false
    body = {}
  }

  if (!response.ok) {
    if (response.status >= 500 && !parsed) throw unreachable()
    const detail = body?.detail
    const message = typeof detail === 'string' ? detail : `Request failed (${response.status})`
    throw new ApiError(message, { status: response.status, fix: body?.fix ?? null })
  }
  return body
}
