import type { Pollutant, ProvinceSnapshot } from '../types'

export interface ObservationContext {
  regions: Array<{ id: string; label: string; value: number; rank: number }>
  totalRegions: number
  average: number | null
  selected: ObservationContext['regions'][number] | null
  difference: number | null
  highest: ObservationContext['regions'][number] | null
  lowest: ObservationContext['regions'][number] | null
}

export function observationContext(snapshots: ProvinceSnapshot[], metric: Pollutant, selectedId: string): ObservationContext {
  const values = snapshots.filter((region) => typeof region[metric] === 'number' && Number.isFinite(region[metric]))
    .map((region) => ({ id: region.provinceCode, label: region.provinceName, value: region[metric] as number }))
    .sort((a, b) => b.value - a.value)
  let rank = 1
  const regions = values.map((region, index) => {
    if (index && region.value !== values[index - 1].value) rank = index + 1
    return { ...region, rank }
  })
  const average = regions.length ? regions.reduce((sum, region) => sum + region.value, 0) / regions.length : null
  const selected = regions.find((region) => region.id === selectedId) ?? null
  return { regions, totalRegions: snapshots.length, average, selected,
    difference: selected && average !== null ? selected.value - average : null,
    highest: regions[0] ?? null, lowest: regions.at(-1) ?? null }
}
