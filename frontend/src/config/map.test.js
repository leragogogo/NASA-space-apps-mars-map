import { expect, test } from 'vitest'
import { AOI, AOI_BOUNDS, MAP_CENTER, MAX_BOUNDS, formatLatLng } from './map.js'

test('AOI bounds are Leaflet order [[south, west], [north, east]]', () => {
  expect(AOI_BOUNDS).toEqual([
    [-13.4, -71.8],
    [-10.0, -68.0],
  ])
})

test('map centre is the middle of the AOI', () => {
  expect(MAP_CENTER[0]).toBeCloseTo(-11.7)
  expect(MAP_CENTER[1]).toBeCloseTo(-69.9)
})

test('max bounds contain the AOI and the whole weather grid', () => {
  const [[s, w], [n, e]] = MAX_BOUNDS
  expect(s).toBeLessThanOrEqual(-30)
  expect(w).toBeLessThanOrEqual(-90)
  expect(n).toBeGreaterThanOrEqual(10)
  expect(e).toBeGreaterThanOrEqual(-50)
  expect(s).toBeLessThanOrEqual(AOI.south)
  expect(w).toBeLessThanOrEqual(AOI.west)
  expect(n).toBeGreaterThanOrEqual(AOI.north)
  expect(e).toBeGreaterThanOrEqual(AOI.east)
})

test('formatLatLng writes south/west for negative values', () => {
  expect(formatLatLng(-11.7, -69.9)).toBe('11.700° S, 69.900° W')
})

test('formatLatLng writes north/east for positive values', () => {
  expect(formatLatLng(4.5, 137.4)).toBe('4.500° N, 137.400° E')
})
