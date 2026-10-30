import type { ConcentrationScale, Pollutant } from '../dashboard/types'
import { METRIC_META } from '../dashboard/model/dashboardSelectors'

export type MapMetric = 'aqi' | Pollutant
export const MAP_METRIC_LABELS: Record<MapMetric, string> = { aqi: 'AQI', ...Object.fromEntries(Object.entries(METRIC_META).map(([key, metric]) => [key, metric.label])) } as Record<MapMetric, string>
export interface MapColorScale { breakpoints: number[]; colors: string[]; labels: string[]; ranges: string[] }
const AQI_SCALE: MapColorScale = {
  breakpoints: [50, 100, 150, 200, 300],
  // VN_AQI 1459 table 1 RGB colors.
  colors: ['#00e400', '#ffff00', '#ff7e00', '#ff0000', '#8f3f97', '#7e0023'],
  labels: ['Tốt', 'Trung bình', 'Kém', 'Xấu', 'Rất xấu', 'Nguy hại'],
  ranges: ['≤ 50', '> 50–100', '> 100–150', '> 150–200', '> 200–300', '> 300'],
}
// Darker companion colors keep AQI text readable on light cards and tooltips.
const AQI_TEXT_COLORS = ['#15803d', '#526b0c', '#866000', '#b45309', '#c62828', '#991b1b']
export function aqiLevel(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return null
  const found = AQI_SCALE.breakpoints.findIndex((cut) => value <= cut)
  const index = found < 0 ? AQI_SCALE.breakpoints.length : found
  return { color: AQI_SCALE.colors[index], textColor: AQI_TEXT_COLORS[index], label: AQI_SCALE.labels[index] }
}
const format = (value: number, metric: MapMetric) => value.toLocaleString('vi-VN', { maximumFractionDigits: metric === 'co' ? 3 : 1 })
export function getMapColorScale(metric: MapMetric, scale?: ConcentrationScale | null): MapColorScale | null {
  if (metric === 'aqi') return AQI_SCALE
  if (!scale || scale.method !== 'absolute_concentration') return null
  const cuts = scale.breakpoints
  if (cuts.length !== 3 || cuts.some((cut, index) => !Number.isFinite(cut) || (index > 0 && cut <= cuts[index - 1]))) return null
  return {
    breakpoints: cuts,
    // Sequential blue display domains are separate from AQI health categories.
    colors: ['#dbeafe', '#93c5fd', '#3b82f6', '#1e3a8a'],
    labels: ['Mức 1', 'Mức 2', 'Mức 3', 'Mức 4'],
    ranges: [`≤ ${format(cuts[0], metric)}`, ...cuts.slice(1).map((cut, index) => `> ${format(cuts[index], metric)}–${format(cut, metric)}`), `> ${format(cuts[cuts.length - 1], metric)}`],
  }
}
export function concentrationColor(value: number | null | undefined, scale: MapColorScale | null): string | null {
  if (value == null || !Number.isFinite(value) || !scale) return null
  const index = scale.breakpoints.findIndex((cut) => value <= cut)
  return scale.colors[index < 0 ? scale.breakpoints.length : index]
}
