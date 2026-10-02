import type { ConcentrationScale, Pollutant } from '../../types/dashboard'
import { METRIC_META } from '../../services/dashboardSelectors'

export type MapMetric = 'aqi' | Pollutant
export const MAP_METRIC_LABELS: Record<MapMetric, string> = { aqi: 'AQI', ...Object.fromEntries(Object.entries(METRIC_META).map(([key, metric]) => [key, metric.label])) } as Record<MapMetric, string>
export interface MapColorScale { breakpoints: number[]; colors: string[]; labels: string[]; ranges: string[] }
const AQI_SCALE: MapColorScale = {
  breakpoints: [50, 100, 150, 200, 300],
  colors: ['#00d12f', '#ffe000', '#ff8500', '#ff2020', '#b977e8', '#b95a78'],
  labels: ['Tốt', 'Trung bình', 'Kém', 'Xấu', 'Rất xấu', 'Nguy hại'],
  ranges: ['≤ 50', '> 50–100', '> 100–150', '> 150–200', '> 200–300', '> 300'],
}
export function aqiLevel(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return null
  const found = AQI_SCALE.breakpoints.findIndex((cut) => value <= cut)
  const index = found < 0 ? AQI_SCALE.breakpoints.length : found
  return { color: AQI_SCALE.colors[index], label: AQI_SCALE.labels[index] }
}
const format = (value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 1 })
export function getMapColorScale(metric: MapMetric, scale?: ConcentrationScale | null): MapColorScale | null {
  if (metric === 'aqi') return AQI_SCALE
  if (!scale || scale.method !== 'absolute_concentration') return null
  const cuts = scale.breakpoints
  if (cuts.length !== 3 || cuts.some((cut, index) => !Number.isFinite(cut) || (index > 0 && cut <= cuts[index - 1]))) return null
  return {
    breakpoints: cuts,
    colors: ['#b6dcf1', '#79b5da', '#4084b8', '#275587'],
    labels: ['Mức 1', 'Mức 2', 'Mức 3', 'Mức 4'],
    ranges: [`≤ ${format(cuts[0])}`, ...cuts.slice(1).map((cut, index) => `> ${format(cuts[index])}–${format(cut)}`), `> ${format(cuts[cuts.length - 1])}`],
  }
}
export function concentrationColor(value: number | null | undefined, scale: MapColorScale | null): string | null {
  if (value == null || !Number.isFinite(value) || !scale) return null
  const index = scale.breakpoints.findIndex((cut) => value <= cut)
  return scale.colors[index < 0 ? scale.breakpoints.length : index]
}
