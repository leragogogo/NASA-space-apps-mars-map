import L from 'leaflet'
import { PANES, POI_CATEGORIES } from '../../../config/layers.js'
import { escapeHtml } from '../../../utils/html.js'

const FALLBACK_COLOR = '#9e9e9e'

export function categoryInfo(id) {
  return POI_CATEGORIES.find((c) => c.id === id) ?? { id, label: id, color: FALLBACK_COLOR }
}

export function poiMarkerStyle(feature) {
  const { color } = categoryInfo(feature.properties.category)
  return { radius: 7, color: '#1b1b1b', weight: 1.5, fillColor: color, fillOpacity: 0.95 }
}

// Leaflet's GeoJSON does not hand its pane option to a custom pointToLayer, so set it here.
export function poiPointToLayer(feature, latlng) {
  return L.circleMarker(latlng, { ...poiMarkerStyle(feature), pane: PANES.poiPoints.name })
}

export function poiPathStyle(feature) {
  const { color } = categoryInfo(feature.properties.category)
  return { color, weight: 2, fillColor: color, fillOpacity: 0.06 }
}

export function poiPopupHtml(props) {
  return [
    '<div class="popup">',
    `<strong>${escapeHtml(props.name)}</strong>`,
    `<div class="popup-meta">${escapeHtml(categoryInfo(props.category).label)}</div>`,
    `<p>${escapeHtml(props.description)}</p>`,
    `<small>${escapeHtml(props.source)}</small>`,
    '</div>',
  ].join('')
}

export function filterPois(collection, categories) {
  const wanted = new Set(categories)
  return {
    type: 'FeatureCollection',
    features: collection.features.filter((f) => wanted.has(f.properties.category)),
  }
}

export function isPointFeature(feature) {
  const type = feature?.geometry?.type
  return type === 'Point' || type === 'MultiPoint'
}

// Points and areas go to separate layers/panes so dots always sit above polygons.
export function splitPois(collection, categories) {
  const { features } = filterPois(collection, categories)
  return {
    areas: { type: 'FeatureCollection', features: features.filter((f) => !isPointFeature(f)) },
    points: { type: 'FeatureCollection', features: features.filter(isPointFeature) },
  }
}
