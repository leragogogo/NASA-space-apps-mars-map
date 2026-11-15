import { expect, test } from 'vitest'
import { layerFour } from '../../../test/fixtures.js'
import { INSUFFICIENT_COLOR, hatchId, weatherCellStyle } from './weatherHelpers.js'

const weather = layerFour('spring')
const [reliable, approximate, insufficient] = weather.features

test('reliable cells are filled solid with the risk colour', () => {
  expect(weatherCellStyle(reliable, weather.legend)).toMatchObject({ fillColor: '#2e7d32', fillOpacity: 0.45 })
})

test('approximate cells are filled with the hatch pattern of their risk', () => {
  expect(hatchId('High')).toBe('hatch-High')
  expect(weatherCellStyle(approximate, weather.legend)).toMatchObject({ fillColor: 'url(#hatch-High)' })
})

test('cells without enough data are grey', () => {
  expect(weatherCellStyle(insufficient, weather.legend)).toMatchObject({ fillColor: INSUFFICIENT_COLOR })
})

test('a risk missing from the legend is shown as grey, not as an invisible cell', () => {
  const odd = { properties: { display_risk: 'Extreme', display_style: 'solid' } }
  expect(weatherCellStyle(odd, weather.legend)).toMatchObject({ fillColor: INSUFFICIENT_COLOR })
})
