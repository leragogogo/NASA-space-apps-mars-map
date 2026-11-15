import { expect, test } from 'vitest'
import { featuresAt, pointInFeature } from './geo.js'

const square = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
const hole = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]
const feature = (geometry) => ({ type: 'Feature', geometry, properties: {} })

test('point inside / outside a square polygon', () => {
  const f = feature({ type: 'Polygon', coordinates: [square] })
  expect(pointInFeature(f, 5, 5)).toBe(true)
  expect(pointInFeature(f, 15, 5)).toBe(false)
  expect(pointInFeature(f, 5, -1)).toBe(false)
})

test('a point inside a hole is outside the polygon', () => {
  const f = feature({ type: 'Polygon', coordinates: [square, hole] })
  expect(pointInFeature(f, 5, 5)).toBe(false)
  expect(pointInFeature(f, 2, 2)).toBe(true)
})

test('MultiPolygon matches any of its parts', () => {
  const far = [[20, 20], [30, 20], [30, 30], [20, 30], [20, 20]]
  const f = feature({ type: 'MultiPolygon', coordinates: [[square], [far]] })
  expect(pointInFeature(f, 25, 25)).toBe(true)
  expect(pointInFeature(f, 5, 5)).toBe(true)
  expect(pointInFeature(f, 15, 15)).toBe(false)
})

test('non-polygon or missing geometry is never inside', () => {
  expect(pointInFeature(feature({ type: 'Point', coordinates: [5, 5] }), 5, 5)).toBe(false)
  expect(pointInFeature(feature(null), 5, 5)).toBe(false)
  expect(pointInFeature(null, 5, 5)).toBe(false)
})

test('featuresAt keeps the features containing the point, in order', () => {
  const a = feature({ type: 'Polygon', coordinates: [square] })
  const b = feature({ type: 'Polygon', coordinates: [[[20, 20], [30, 20], [30, 30], [20, 20]]] })
  const c = feature({ type: 'Polygon', coordinates: [[[1, 1], [9, 1], [9, 9], [1, 9], [1, 1]]] })
  expect(featuresAt([a, b, c], 5, 5)).toEqual([a, c])
  expect(featuresAt([a, b, c], 50, 50)).toEqual([])
})
