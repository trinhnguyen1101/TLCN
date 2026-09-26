import type { ConcentrationScale } from '../../types/dashboard'

export type MapMetric = 'aqi' | 'pm1' | 'pm25' | 'pm10'

export const MAP_METRIC_LABELS: Record<MapMetric, string> = {
  aqi: 'AQI', pm1: 'PM1', pm25: 'PM2.5', pm10: 'PM10',
}

export interface MapColorScale {
  breakpoints: number[]
  colors: string[]
  labels: string[]
  ranges: string[]
}

// Saturated green → yellow → orange → bright red.
const LEVEL_COLORS = ['#00d12f', '#ffe000', '#ff8500', '#ff2020']
const LEVEL_LABELS = ['Tốt', 'Trung bình', 'Kém', 'Xấu']

const AQI_SCALE: MapColorScale = {
  breakpoints: [50, 100, 150],
  colors: LEVEL_COLORS,
  labels: LEVEL_LABELS,
  ranges: ['≤ 50', '> 50–100', '> 100–150', '> 150'],
}

const format = (value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 1 })

/** Both the province fill and the legend use these exact API-supplied cutoffs. */
export function getMapColorScale(metric: MapMetric, scale?: ConcentrationScale | null): MapColorScale | null {
  if (metric === 'aqi') return AQI_SCALE
  if (!scale || scale.method !== 'absolute_concentration') return null
  const cuts = scale.breakpoints
  if (cuts.some((cut, index) => !Number.isFinite(cut) || (index > 0 && cut <= cuts[index - 1])) || cuts.length !== 3) return null
  return {
    breakpoints: cuts,
    colors: LEVEL_COLORS,
    labels: LEVEL_LABELS,
    ranges: [
      `≤ ${format(cuts[0])}`,
      ...cuts.slice(1).map((cut, index) => `> ${format(cuts[index])}–${format(cut)}`),
      `> ${format(cuts[cuts.length - 1])}`,
    ],
  }
}

export function concentrationColor(value: number | null | undefined, scale: MapColorScale | null): string | null {
  if (value == null || !Number.isFinite(value) || !scale) return null
  const index = scale.breakpoints.findIndex((cut) => value <= cut)
  return scale.colors[index < 0 ? scale.breakpoints.length : index]
}
