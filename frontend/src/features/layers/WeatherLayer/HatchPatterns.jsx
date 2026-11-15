import { hatchId } from './weatherHelpers.js'

// Hidden SVG with one diagonal-hatch <pattern> per risk colour; weather cells reference them by id.
export default function HatchPatterns({ colors }) {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true" focusable="false">
      <defs>
        {Object.entries(colors).map(([risk, color]) => (
          <pattern
            key={risk}
            id={hatchId(risk)}
            width="8"
            height="8"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="8" height="8" fill={color} fillOpacity="0.25" />
            <line x1="0" y1="0" x2="0" y2="8" stroke={color} strokeWidth="3" />
          </pattern>
        ))}
      </defs>
    </svg>
  )
}
