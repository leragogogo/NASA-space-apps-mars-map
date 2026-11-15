import { useEffect, useState } from 'react'

/**
 * Loads one layer's data. Re-runs `load` whenever `enabled` or any value in `deps` changes.
 * Returns { status: 'idle' | 'loading' | 'ready' | 'error', data, error }.
 * While `enabled` is false the status is always 'idle' with no error (any `data` already loaded is kept).
 * While reloading, the previous data stays available, so the map does not flash empty.
 */
export function useLayer(load, deps, enabled = true) {
  const [state, setState] = useState({ status: enabled ? 'loading' : 'idle', data: null, error: null })

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false
    setState((prev) => ({ status: 'loading', data: prev.data, error: null }))
    load().then(
      (data) => !cancelled && setState({ status: 'ready', data, error: null }),
      (error) => !cancelled && setState({ status: 'error', data: null, error }),
    )
    return () => {
      cancelled = true
    }
    // `load` is usually an inline arrow; the caller lists what it depends on in `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps])

  return enabled ? state : { ...state, status: 'idle', error: null }
}
