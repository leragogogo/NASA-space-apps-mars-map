import L from 'leaflet'
import { expect, test } from 'vitest'
import { layerThree } from '../../../test/fixtures.js'
import { categoryInfo, filterPois, isPointFeature, splitPois, poiMarkerStyle, poiPathStyle, poiPointToLayer, poiPopupHtml } from './poiHelpers.js'

const [mineral, zone] = layerThree.features

test('categoryInfo returns label and colour of a known category', () => {
  expect(categoryInfo('mineral')).toEqual({ id: 'mineral', label: 'Minerals', color: '#00bcd4' })
})

test('categoryInfo falls back to grey for an unknown category', () => {
  expect(categoryInfo('mystery')).toEqual({ id: 'mystery', label: 'mystery', color: '#9e9e9e' })
})

test('point markers are filled with the category colour', () => {
  expect(poiMarkerStyle(mineral)).toMatchObject({ fillColor: '#00bcd4', radius: 7 })
})

test('polygons are outlined in the category colour with a light fill', () => {
  expect(poiPathStyle(zone)).toMatchObject({ color: '#ffd600', fillColor: '#ffd600', fillOpacity: 0.06 })
})

test('popup shows name, category, description and source, escaped', () => {
  const html = poiPopupHtml({ ...mineral.properties, name: '<b>Silica</b>' })
  expect(html).toContain('&lt;b&gt;Silica&lt;/b&gt;')
  expect(html).toContain('Minerals')
  expect(html).toContain('Orbital detection of silica.')
  expect(html).toContain('Aqueous Mineral Distribution (NASA Trek)')
})

test('filterPois keeps only the chosen categories', () => {
  expect(filterPois(layerThree, ['mineral']).features).toEqual([mineral])
  expect(filterPois(layerThree, []).features).toEqual([])
})

test('isPointFeature is true for Point and MultiPoint only', () => {
  expect(isPointFeature({ geometry: { type: 'Point' } })).toBe(true)
  expect(isPointFeature({ geometry: { type: 'MultiPoint' } })).toBe(true)
  expect(isPointFeature({ geometry: { type: 'Polygon' } })).toBe(false)
  expect(isPointFeature({ geometry: null })).toBe(false)
})

test('splitPois separates points from areas after filtering by category', () => {
  const all = splitPois(layerThree, ['mineral', 'exploration_zone'])
  expect(all.points.features).toEqual([mineral])
  expect(all.areas.features).toEqual([zone])
  const some = splitPois(layerThree, ['mineral'])
  expect(some.areas.features).toEqual([])
  expect(some.points.type).toBe('FeatureCollection')
})

test('poiPointToLayer puts the dot in the poi-points pane with category colour', () => {
  const layer = poiPointToLayer(mineral, L.latLng(-12, -68))
  expect(layer.options.pane).toBe('poi-points')
  expect(layer.options.fillColor).toBe('#00bcd4')
  expect(layer.options.radius).toBe(7)
})
