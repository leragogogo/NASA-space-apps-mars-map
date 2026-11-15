import { act, renderHook, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { ApiError } from '../api/marsApi.js'
import { useLayer } from './useLayer.js'

test('loads data when enabled', async () => {
  const load = vi.fn().mockResolvedValue({ a: 1 })
  const { result } = renderHook(() => useLayer(load, []))
  expect(result.current.status).toBe('loading')
  await waitFor(() => expect(result.current.status).toBe('ready'))
  expect(result.current.data).toEqual({ a: 1 })
  expect(load).toHaveBeenCalledTimes(1)
})

test('stays idle and does not load when disabled', () => {
  const load = vi.fn()
  const { result } = renderHook(() => useLayer(load, [], false))
  expect(result.current.status).toBe('idle')
  expect(load).not.toHaveBeenCalled()
})

test('reports errors', async () => {
  const load = vi.fn().mockRejectedValue(new ApiError('Weather files not found', { status: 503 }))
  const { result } = renderHook(() => useLayer(load, []))
  await waitFor(() => expect(result.current.status).toBe('error'))
  expect(result.current.error.message).toBe('Weather files not found')
  expect(result.current.data).toBeNull()
})

test('reloads when deps change and ignores the stale response', async () => {
  const resolvers = {}
  const load = vi.fn((season) => new Promise((resolve) => (resolvers[season] = resolve)))
  const { result, rerender } = renderHook(({ season }) => useLayer(() => load(season), [season]), {
    initialProps: { season: 'spring' },
  })
  rerender({ season: 'winter' })
  await act(async () => resolvers.winter('W'))
  await act(async () => resolvers.spring('S'))
  expect(result.current.data).toBe('W')
  expect(result.current.status).toBe('ready')
  expect(load).toHaveBeenCalledTimes(2)
})

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

test('loads when enabled switches from false to true', async () => {
  const d = deferred()
  const load = vi.fn(() => d.promise)
  const { result, rerender } = renderHook(({ enabled }) => useLayer(load, [], enabled), {
    initialProps: { enabled: false },
  })
  expect(load).not.toHaveBeenCalled()
  rerender({ enabled: true })
  expect(load).toHaveBeenCalledTimes(1)
  expect(result.current.status).toBe('loading')
  await act(async () => d.resolve('D'))
  expect(result.current.status).toBe('ready')
  expect(result.current.data).toBe('D')
})

test('keeps the previous data while reloading after deps change', async () => {
  const resolvers = {}
  const load = vi.fn((season) => new Promise((resolve) => (resolvers[season] = resolve)))
  const { result, rerender } = renderHook(({ season }) => useLayer(() => load(season), [season]), {
    initialProps: { season: 'spring' },
  })
  await act(async () => resolvers.spring('S'))
  expect(result.current.status).toBe('ready')
  rerender({ season: 'winter' })
  expect(result.current.status).toBe('loading')
  expect(result.current.data).toBe('S')
  await act(async () => resolvers.winter('W'))
  expect(result.current.status).toBe('ready')
  expect(result.current.data).toBe('W')
})

test('disabling mid-load reports idle and ignores the late response', async () => {
  const d = deferred()
  const load = vi.fn(() => d.promise)
  const { result, rerender } = renderHook(({ enabled }) => useLayer(load, [], enabled), {
    initialProps: { enabled: true },
  })
  expect(result.current.status).toBe('loading')
  rerender({ enabled: false })
  expect(result.current.status).toBe('idle')
  await act(async () => d.resolve('late'))
  expect(result.current.status).toBe('idle')
})

test('disabling after an error reports idle with no error', async () => {
  const load = vi.fn().mockRejectedValue(new ApiError('boom', { status: 503 }))
  const { result, rerender } = renderHook(({ enabled }) => useLayer(load, [], enabled), {
    initialProps: { enabled: true },
  })
  await waitFor(() => expect(result.current.status).toBe('error'))
  rerender({ enabled: false })
  expect(result.current.status).toBe('idle')
  expect(result.current.error).toBeNull()
})
