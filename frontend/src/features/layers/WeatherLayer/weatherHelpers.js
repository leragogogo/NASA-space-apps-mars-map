export const INSUFFICIENT_COLOR = '#9e9e9e'

export const hatchId = (risk) => `hatch-${risk}`

// Data-sufficiency rule (SKILL.md §6): solid = reliable, hatched = approximate, grey = not enough data.
export function weatherCellStyle(feature, legend) {
  const { display_risk: risk, display_style: style } = feature.properties
  const color = legend[risk]
  if (style === 'grey' || !color) {
    return { color: '#757575', weight: 0.5, fillColor: INSUFFICIENT_COLOR, fillOpacity: 0.35 }
  }
  if (style === 'hatched') {
    return { color, weight: 0.5, fillColor: `url(#${hatchId(risk)})`, fillOpacity: 0.8 }
  }
  return { color, weight: 0.5, fillColor: color, fillOpacity: 0.45 }
}
