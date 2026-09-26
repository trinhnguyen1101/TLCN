import type {
  AdminDashboardData,
  AdminTrendRecord,
  ChartPoint,
  DashboardFiltersValue,
  Pollutant,
  PriorityArea,
} from '../types/dashboard'
import type { HorizontalBarPoint } from '../features/analytics/HorizontalBarChart'

export const ADMIN_METRIC_META: Record<string, { label: string; unit: string }> = {
  pm25: { label: 'PM2.5', unit: 'µg/m³' }, pm10: { label: 'PM10', unit: 'µg/m³' },
  o3: { label: 'O₃', unit: 'µg/m³' }, no2: { label: 'NO₂', unit: 'µg/m³' },
  so2: { label: 'SO₂', unit: 'µg/m³' }, co: { label: 'CO', unit: 'mg/m³' },
  pm1: { label: 'PM1', unit: 'µg/m³' }, aod550: { label: 'AOD 550 nm', unit: '1' },
  o3Column: { label: 'O₃ tổng cột', unit: 'mg/m²' }, no2Column: { label: 'NO₂ tổng cột', unit: 'mg/m²' },
  so2Column: { label: 'SO₂ tổng cột', unit: 'mg/m²' }, coColumn: { label: 'CO tổng cột', unit: 'mg/m²' },
  t2m: { label: 'Nhiệt độ 2 m', unit: '°C' }, d2m: { label: 'Điểm sương 2 m', unit: '°C' },
  sp: { label: 'Áp suất bề mặt', unit: 'hPa' }, mslp: { label: 'Áp suất mực biển', unit: 'hPa' },
  u10: { label: 'Gió 10 m hướng đông', unit: 'm/s' }, v10: { label: 'Gió 10 m hướng bắc', unit: 'm/s' },
}

export interface AdminDashboardView {
  availableMetrics: Pollutant[]
  pollutantOptions: Array<{ value: Pollutant; label: string }>
  years: number[]
  currentYear: number | undefined
  selectedPollutant: Pollutant
  metric: { label: string; unit: string }
  scopeLabel: string
  chartPoints: ChartPoint[]
  provinceRanking: HorizontalBarPoint[]
  sectorRanking: HorizontalBarPoint[]
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
  return (!start || record.date >= start) && (!end || record.date <= end)
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
  let availableMetrics = Object.keys(data?.metadata?.metrics ?? {}).filter((key): key is Pollutant => key in ADMIN_METRIC_META)
  if (!availableMetrics.length) {
    availableMetrics = Object.keys(ADMIN_METRIC_META).filter((key) => trends.some((record) => isNumber(record[key as keyof AdminTrendRecord]))) as Pollutant[]
  }
  if (!availableMetrics.length) availableMetrics = ['pm25', 'pm10', 'o3', 'no2', 'so2', 'co']
  const pollutantOptions = availableMetrics.map((value) => ({ value, label: ADMIN_METRIC_META[value].label }))
  const years = [...new Set(trends.map((record) => Number(record.date.slice(0, 4))).filter(Number.isFinite))].sort((a, b) => b - a)
  const currentYear = filters.year === 'all' ? years[0] : filters.year
  const selectedPollutant = availableMetrics.includes(filters.pollutant) ? filters.pollutant : availableMetrics[0] ?? 'pm25'
  const metric = { ...ADMIN_METRIC_META[selectedPollutant], unit: data?.metadata?.metrics?.[selectedPollutant]?.unit ?? ADMIN_METRIC_META[selectedPollutant].unit }
  const scopeLabel = filters.provinceCode === 'all'
    ? 'Toàn quốc'
    : snapshots.find((province) => province.provinceCode === filters.provinceCode)?.provinceName ?? 'Toàn quốc'
  const trendRecords = trends.filter((record) => matchesPeriod(record, filters))
  const currentRecords = currentYear === undefined ? [] : trends.filter((record) => matchesPeriod(record, filters, currentYear))
  const previousRecords = currentYear === undefined ? [] : trends.filter((record) => matchesPeriod(record, filters, currentYear - 1))

  const chartGroups = new Map<string, number[]>()
  for (const record of trendRecords) {
    const value = record[selectedPollutant]
    if (!isNumber(value)) continue
    const key = record.date.slice(0, 7)
    chartGroups.set(key, [...(chartGroups.get(key) ?? []), value])
  }
  const chartPoints = [...chartGroups].sort(([a], [b]) => a.localeCompare(b)).map(([date, values]) => ({
    label: filters.year === 'all' ? `T${Number(date.slice(5))}/${date.slice(2, 4)}` : `T${Number(date.slice(5))}`,
    value: Number((mean(values) ?? 0).toFixed(1)),
  }))

  const provinceGroups = new Map<string, number[]>()
  currentRecords.forEach((record) => {
    if (isNumber(record.pm25)) provinceGroups.set(record.provinceCode, [...(provinceGroups.get(record.provinceCode) ?? []), record.pm25])
  })
  const provinceRanking = [...provinceGroups].map(([id, values]) => ({
    id,
    label: snapshots.find((province) => province.provinceCode === id)?.provinceName ?? id,
    value: Number((mean(values) ?? 0).toFixed(1)),
  })).sort((a, b) => b.value - a.value)

  const filteredEmissions = emissions.filter((record) => {
    if (currentYear !== undefined && record.year !== currentYear) return false
    if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
    if (filters.month !== 'all' && record.month !== filters.month) return false
    if (filters.sector !== 'all' && record.sector !== filters.sector) return false
    const date = `${record.year}-${String(record.month).padStart(2, '0')}-15`
    const start = filters.startDate && currentYear !== undefined ? `${currentYear}${filters.startDate.slice(4)}` : filters.startDate
    const end = filters.endDate && currentYear !== undefined ? `${currentYear}${filters.endDate.slice(4)}` : filters.endDate
    return (!start || date >= start) && (!end || date <= end)
  })
  const sectorGroups = new Map<string, number>()
  filteredEmissions.forEach((record) => sectorGroups.set(record.sector, (sectorGroups.get(record.sector) ?? 0) + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0)))
  const sectorRanking = [...sectorGroups].map(([id, value]) => ({ id, label: id, value: Math.round(value) })).sort((a, b) => b.value - a.value)
  const totalEmissions = filteredEmissions.length
    ? filteredEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0)
    : null
  const currentPm25 = mean(currentRecords.map((record) => record.pm25))
  const currentAqi = mean(currentRecords.map((record) => record.aqi))
  const previousPm25 = mean(previousRecords.map((record) => record.pm25))
  const yoy = currentPm25 !== null && previousPm25 !== null && previousPm25 !== 0
    ? (currentPm25 - previousPm25) / previousPm25 * 100
    : null
  const scopedSummaries = summaries.filter((summary) => summary.year === currentYear && (filters.provinceCode === 'all' || summary.provinceCode === filters.provinceCode))
  const visibleMonths = new Set(currentRecords.map((record) => record.date.slice(0, 7))).size
  const exceedanceAverage = mean(scopedSummaries.map((summary) => summary.exceedanceDays))
  const exceedanceDays = exceedanceAverage === null || !visibleMonths ? null : Math.round(exceedanceAverage * visibleMonths / 12)

  const priorityAreaRows = (data?.priorityAreas ?? [])
    .filter((area) => filters.provinceCode === 'all' || area.provinceCode === filters.provinceCode)
    .map((area) => {
      const areaCurrent = currentRecords.filter((record) => record.provinceCode === area.provinceCode)
      const areaPrevious = previousRecords.filter((record) => record.provinceCode === area.provinceCode)
      const pm25Average = mean(areaCurrent.map((record) => record.pm25)) ?? area.pm25Average
      const currentMetric = mean(areaCurrent.map((record) => record[selectedPollutant]))
      const previousMetric = mean(areaPrevious.map((record) => record[selectedPollutant]))
      const change = currentMetric !== null && previousMetric !== null && previousMetric !== 0
        ? (currentMetric - previousMetric) / previousMetric * 100
        : selectedPollutant === 'pm25' ? area.yearOverYearPercent : null
      const areaEmissions = filteredEmissions.filter((record) => record.provinceCode === area.provinceCode)
      const emissionsTotal = areaEmissions.length
        ? areaEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0)
        : area.totalEmissions
      const sectors = new Map<string, number>()
      areaEmissions.forEach((record) => {
        if (isNumber(record.emissionTonnes)) sectors.set(record.sector, (sectors.get(record.sector) ?? 0) + record.emissionTonnes)
      })
      const mainEmissionSector = [...sectors].sort((a, b) => b[1] - a[1])[0]?.[0] ?? area.mainEmissionSector
      const visibleAreaMonths = new Set(areaCurrent.map((record) => record.date.slice(0, 7))).size
      const exceedanceDays = area.exceedanceDays === null ? null : Math.round(area.exceedanceDays * visibleAreaMonths / 12)
      return { ...area, pm25Average, yearOverYearPercent: change, exceedanceDays, totalEmissions: emissionsTotal, mainEmissionSector, trend: trendFromChange(change) }
    })

  const fastestProvince = [...priorityAreaRows]
    .filter((area) => area.yearOverYearPercent !== null)
    .sort((a, b) => (b.yearOverYearPercent ?? 0) - (a.yearOverYearPercent ?? 0))[0]
  return {
    availableMetrics, pollutantOptions, years, currentYear, selectedPollutant, metric, scopeLabel,
    chartPoints, provinceRanking, sectorRanking, totalEmissions, currentPm25, currentAqi, yoy, exceedanceDays,
    priorityAreaRows, bestProvince: provinceRanking[0], fastestProvince, topSector: sectorRanking[0],
  }
}
