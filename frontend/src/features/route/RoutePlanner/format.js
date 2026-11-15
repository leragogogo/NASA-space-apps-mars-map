// Number formatting for the route planner, in the style of a map app.
const one = (value) => Number(value).toLocaleString('en-US', { maximumFractionDigits: 1 })

export const kilograms = one
export const coordinate = (point) => `${point.lat.toFixed(3)}, ${point.lon.toFixed(3)}`
export const grams = (g) => (g >= 1000 ? `${one(g / 1000)} kg` : `${one(g)} g`)
export const wattHours = (wh) => (wh >= 1000 ? `${one(wh / 1000)} kWh` : `${one(wh)} Wh`)

export function formatDuration(seconds) {
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} h ${m} min` : `${h} h`
}
