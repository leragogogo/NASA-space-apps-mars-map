// Ray casting; ring = [[lon, lat], ...].
function inRing(ring, lng, lat) {
  let inside = false
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i]
    const [xj, yj] = ring[j]
    if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside
  }
  return inside
}

// Outer ring minus holes.
function inPolygon(rings, lng, lat) {
  const [outer, ...holes] = rings
  return !!outer && inRing(outer, lng, lat) && !holes.some((h) => inRing(h, lng, lat))
}

export function pointInFeature(feature, lng, lat) {
  const geometry = feature?.geometry
  if (geometry?.type === 'Polygon') return inPolygon(geometry.coordinates, lng, lat)
  if (geometry?.type === 'MultiPolygon') return geometry.coordinates.some((p) => inPolygon(p, lng, lat))
  return false
}

export function featuresAt(features, lng, lat) {
  return features.filter((f) => pointInFeature(f, lng, lat))
}
