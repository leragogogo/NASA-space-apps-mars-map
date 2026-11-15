// Small inline icons shared by the panels (stroke = currentColor, so they follow the text colour).
const Svg = ({ children, size = 18 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
)

export const BestIcon = () => (
  <Svg><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" /></Svg>
)

export const WalkIcon = () => (
  <Svg><circle cx="13" cy="4" r="2" /><path d="M10 21l2-6 3 3v3" /><path d="M7 12l3-4 4 2 3 3" /><path d="M12 15l-1-5" /></Svg>
)

export const RoverIcon = () => (
  <Svg><path d="M3 15h18v-3l-3-5H8l-3 5H3z" /><circle cx="7" cy="17" r="2" /><circle cx="17" cy="17" r="2" /></Svg>
)

export const ChevronIcon = ({ up }) => (
  <Svg size={16}><path d={up ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} /></Svg>
)

export const PlusIcon = () => <Svg size={16}><path d="M12 5v14M5 12h14" /></Svg>

export const CloseIcon = () => <Svg size={14}><path d="M6 6l12 12M18 6L6 18" /></Svg>

// Hide a window: an arrow tucking it away. Layers / eye icons for the map buttons.
export const HideIcon = () => <Svg size={16}><path d="M15 6l-6 6 6 6" /></Svg>

export const LayersIcon = () => (
  <Svg size={16}><path d="M12 3l9 5-9 5-9-5z" /><path d="M3 13l9 5 9-5" /></Svg>
)

export const EyeIcon = ({ off }) => (
  <Svg size={16}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" />
    {off && <path d="M3 3l18 18" />}
  </Svg>
)
