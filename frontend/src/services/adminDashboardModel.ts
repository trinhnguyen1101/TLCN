import type {
  AdminDashboardData,
  AdminTrendRecord,
  DashboardFiltersValue,
  Pollutant,
  PriorityArea,
} from '../types/dashboard'
import type { HorizontalBarPoint } from '../features/analytics/HorizontalBarChart'

import { METRIC_META } from './metricMetadata.ts'


export interface AdminDashboardView {
  availableMetrics: Pollutant[]
  pollutantOptions: Array<{ value: Pollutant; label: string }>
  years: number[]
  currentYear: number | undefined
  selectedPollutant: Pollutant
  metric: { label: string; unit: string }
  scopeLabel: string
  provinceRanking: HorizontalBarPoint[]
  sectorRanking: HorizontalBarPoint[]
  filteredEmissionRecords: AdminDashboardData['emissionRecords']
  totalEmissions: number | null
  currentPm25: number | null
  currentAqi: number | null
  yoy: number | null
  exceedanceDays: number | null
  priorityAreaRows: PriorityArea[]
  bestProvince: HorizontalBarPoint | undefined
  fastestProvince: PriorityArea | undefined
  topSector: HorizontalBarPoint | undefined
}

const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const mean = (values: Array<number | null | undefined>) => {
  const valid = values.filter(isNumber)
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
}

function matchesPeriod(record: AdminTrendRecord, filters: DashboardFiltersValue, year?: number) {
  if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
  if (year !== undefined && Number(record.date.slice(0, 4)) !== year) return false
  if (year === undefined && filters.year !== 'all' && Number(record.date.slice(0, 4)) !== filters.year) return false
  if (filters.month !== 'all' && Number(record.date.slice(5, 7)) !== filters.month) return false
  const start = filters.startDate && year !== undefined ? `${year}${filters.startDate.slice(4)}` : filters.startDate
  const end = filters.endDate && year !== undefined ? `${year}${filters.endDate.slice(4)}` : filters.endDate
  return (!start || record.date.slice(0, 7) >= start.slice(0, 7)) && (!end || record.date.slice(0, 7) <= end.slice(0, 7))
}

function trendFromChange(change: number | null): PriorityArea['trend'] {
  if (change === null) return null
  if (change >= 8) return 'up'
  if (change > 2) return 'slight-up'
  if (change <= -2) return 'down'
  return 'steady'
}

export function buildAdminDashboardView(
  data: AdminDashboardData | null,
  filters: DashboardFiltersValue,
): AdminDashboardView {
  const snapshots = data?.provinceSnapshots ?? []
  const trends = data?.dashboardTrendRecords ?? []
  const emissions = data?.emissionRecords ?? []
  const summaries = data?.annualProvinceSummaries ?? []
  let availableMetrics = Object.keys(data?.metadata?.metrics ?? {}).filter((key): key is Pollutant => key in METRIC_META)
  if (!availableMetrics.length) {
    availableMetrics = Object.keys(METRIC_META).filter((key) => trends.some((record) => isNumber(record[key as keyof AdminTrendRecord]))) as Pollutant[]
  }
  if (!availableMetrics.length) availableMetrics = ['pm25', 'pm10', 'o3', 'no2', 'so2', 'co']
  const pollutantOptions = availableMetrics.map((value) => ({ value, label: METRIC_META[value].label }))
  const years = [...new Set(trends.map((record) => Number(record.date.slice(0, 4))).filter(Number.isFinite))].sort((a, b) => b - a)
  const currentYear = filters.year === 'all' ? years[0] : filters.year
  const selectedPollutant = availableMetrics.includes(filters.pollutant) ? filters.pollutant : availableMetrics[0] ?? 'pm25'
  const metric = { ...METRIC_META[selectedPollutant], unit: data?.metadata?.metrics?.[selectedPollutant]?.unit ?? METRIC_META[selectedPollutant].unit }
  const scopeLabel = filters.provinceCode === 'all'
    ? 'Toàn quốc'
    : snapshots.find((province) => province.provinceCode === filters.provinceCode)?.provinceName ?? 'Toàn quốc'
  const trendRecords = trends.filter((record) => matchesPeriod(record, filters))
  const currentRecords = trendRecords
  const previousByMonth = new Map(trends.map(record => [`${record.provinceCode}:${record.date.slice(0, 7)}`, record.pm25]))
  const pairedChange = (records: AdminTrendRecord[]) => {
    const pairs = records.flatMap(record => {
      const previous = previousByMonth.get(`${record.provinceCode}:${Number(record.date.slice(0, 4)) - 1}${record.date.slice(4, 7)}`)
      return isNumber(record.pm25) && isNumber(previous) ? [{ current: record.pm25, previous }] : []
    })
    const current = mean(pairs.map(pair => pair.current))
    const previous = mean(pairs.map(pair => pair.previous))
    return current !== null && previous !== null && previous !== 0 ? (current - previous) / previous * 100 : null
  }

  const provinceGroups = new Map<string, number[]>()
  trends.filter(record => matchesPeriod(record, filters)).forEach((record) => {
    if (isNumber(record.pm25)) provinceGroups.set(record.provinceCode, [...(provinceGroups.get(record.provinceCode) ?? []), record.pm25])
  })
  const provinceRanking = [...provinceGroups].map(([id, values]) => ({
    id,
    label: snapshots.find((province) => province.provinceCode === id)?.provinceName ?? id,
    value: Number((mean(values) ?? 0).toFixed(1)),
  })).sort((a, b) => b.value - a.value)

  const filteredEmissions = emissions.filter((record) => {
    if (filters.year !== 'all' && record.year !== filters.year) return false
    if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
    if (filters.month !== 'all' && record.month !== filters.month) return false
    if (filters.sector !== 'all' && record.sector !== filters.sector) return false
    const date = `${record.year}-${String(record.month).padStart(2, '0')}`
    return (!filters.startDate || date >= filters.startDate.slice(0, 7)) && (!filters.endDate || date <= filters.endDate.slice(0, 7))
  })
  const sectorGroups = new Map<string, number>()
  filteredEmissions.forEach((record) => sectorGroups.set(record.sector, (sectorGroups.get(record.sector) ?? 0) + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0)))
  const sectorRanking = [...sectorGroups].map(([id, value]) => ({ id, label: id, value: Math.round(value) })).sort((a, b) => b.value - a.value)
  const totalEmissions = filteredEmissions.length
    ? filteredEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0)
    : null
  const currentPm25 = mean(currentRecords.map((record) => record.pm25))
  const currentAqi = mean(currentRecords.map((record) => record.aqi))
  const yoy = pairedChange(currentRecords)
  // Annual exceedance counts cannot be prorated to arbitrary months or days.
  const fullYear = filters.year !== 'all' && filters.month === 'all' && !filters.startDate && !filters.endDate
  const scopedSummaries = summaries.filter(summary => summary.year === filters.year && summary.provinceCode === filters.provinceCode)
  const exceedanceDays = fullYear && scopedSummaries.length === 1 ? scopedSummaries[0].exceedanceDays : null

  const priorityAreaRows = (data?.priorityAreas ?? [])
    .filter((area) => filters.provinceCode === 'all' || area.provinceCode === filters.provinceCode)
    .map((area) => {
      const areaCurrent = currentRecords.filter((record) => record.provinceCode === area.provinceCode)
      const pm25Average = mean(areaCurrent.map((record) => record.pm25))
      const change = pairedChange(areaCurrent)
      const areaEmissions = filteredEmissions.filter((record) => record.provinceCode === area.provinceCode)
      const emissionsTotal = areaEmissions.length
        ? areaEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0)
        : null
      const sectors = new Map<string, number>()
      areaEmissions.forEach((record) => {
        if (isNumber(record.emissionTonnes)) sectors.set(record.sector, (sectors.get(record.sector) ?? 0) + record.emissionTonnes)
      })
      const mainEmissionSector = [...sectors].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
      const exceedanceDays = fullYear ? summaries.find(summary => summary.year === filters.year && summary.provinceCode === area.provinceCode)?.exceedanceDays ?? null : null
      return { ...area, pm25Average, yearOverYearPercent: change, exceedanceDays, totalEmissions: emissionsTotal, mainEmissionSector, trend: trendFromChange(change) }
    })

  const fastestProvince = [...priorityAreaRows]
    .filter((area) => area.yearOverYearPercent !== null)
    .sort((a, b) => (b.yearOverYearPercent ?? 0) - (a.yearOverYearPercent ?? 0))[0]
  return {
    availableMetrics, pollutantOptions, years, currentYear, selectedPollutant, metric, scopeLabel,
    provinceRanking, sectorRanking, filteredEmissionRecords: filteredEmissions, totalEmissions, currentPm25, currentAqi, yoy, exceedanceDays,
    priorityAreaRows, bestProvince: provinceRanking[0], fastestProvince, topSector: sectorRanking[0],
  }
}
