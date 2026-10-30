import { DEFAULT_RESOLUTION } from './resolution'
import type { AdminTrendRecord, DashboardData, DashboardFiltersValue, EmissionRecord, Pollutant, ProvinceSnapshot } from '../types'
import { chartKey, chartLabel, inDateRange } from './temporal'
import { formatDateTime, isIsoDate, shiftDateYear } from '../../../utils/dates'
import { observationContext } from './observationInsights'

export const METRIC_META: Record<Pollutant, { label: string; unit: string }> = {
  aqi: { label: 'AQI', unit: '' },
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
export const BASIC_POLLUTANTS: Pollutant[] = ['pm25', 'pm10', 'pm1', 'no2', 'so2', 'co', 'o3']
export function metricCategory(key: Pollutant): 'pollutants' | 'columns' | 'weather' {
  return ['t2m','d2m','sp','mslp','u10','v10'].includes(key) ? 'weather' : key.endsWith('Column') || key === 'aod550' ? 'columns' : 'pollutants'
}
export const DEFAULT_FILTERS: DashboardFiltersValue = {
  resolution: DEFAULT_RESOLUTION, provinceCode: 'all', pollutant: 'pm25', year: 'all', month: 'all', startDate: '', endDate: '', sector: 'all',
}
export const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
export const mean = (values: Array<number | null | undefined>) => {
  const valid = values.filter(isNumber)
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
}
export function weightedMetricMean(rows: AdminTrendRecord[], metric: Pollutant) {
  let total = 0, count = 0
  for (const row of rows) {
    const value = row[metric]
    const weight = row.metricSampleCounts?.[metric] ?? 1
    if (isNumber(value) && isNumber(weight) && weight > 0) { total += value * weight; count += weight }
  }
  return count ? total / count : null
}
export const hasPeriodFilter = (filters: DashboardFiltersValue) => filters.year !== 'all' || filters.month !== 'all' || Boolean(filters.startDate || filters.endDate)

export const hasDateRange = (filters: DashboardFiltersValue) => Boolean(filters.startDate || filters.endDate)

export function updateDashboardFilter<K extends keyof DashboardFiltersValue>(filters: DashboardFiltersValue, key: K, value: DashboardFiltersValue[K]): DashboardFiltersValue {
  const next = { ...filters, [key]: value }
  if (key === 'startDate' || key === 'endDate') { next.year = 'all'; next.month = 'all' }
  if (key === 'year' || key === 'month') { next.startDate = ''; next.endDate = '' }
  return next
}

export function validDateRange(filters: DashboardFiltersValue) {
  const valid = (value: string) => !value || isIsoDate(value.slice(0, 10))
    && (value.length === 10 || /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?$/.test(value) && Number.isFinite(Date.parse(`${value.replace(/Z$/, '')}Z`)))
  return valid(filters.startDate) && valid(filters.endDate)
    && (!filters.startDate || !filters.endDate || filters.startDate <= filters.endDate)
}

export function matchesPeriod(record: { date: string; provinceCode: string }, filters: DashboardFiltersValue, includeProvince = true, aggregation?: string) {
  if (!validDateRange(filters)) return false
  const custom = hasDateRange(filters)
  // A monthly mean represents the whole month, regardless of its timestamp's day.
  const monthly = aggregation === 'monthly_mean' || filters.resolution === 'monthly'
  return (!includeProvince || filters.provinceCode === 'all' || record.provinceCode === filters.provinceCode)
    && (custom || filters.year === 'all' || Number(record.date.slice(0, 4)) === filters.year)
    && (custom || filters.month === 'all' || Number(record.date.slice(5, 7)) === filters.month)
    && inDateRange(record.date, filters.startDate, filters.endDate, monthly ? 'monthly' : filters.resolution)
}

export function matchesEmissionPeriod(record: EmissionRecord, filters: DashboardFiltersValue) {
  return matchesPeriod({ provinceCode: record.provinceCode, date: `${record.year}-${String(record.month).padStart(2, '0')}-01` }, filters, true, 'monthly_mean')
    && (filters.sector === 'all' || record.sector === filters.sector)
}

export function comparisonYear(filters: DashboardFiltersValue) {
  return hasDateRange(filters) ? Number((filters.endDate || filters.startDate).slice(0, 4)) : filters.year === 'all' ? null : filters.year
}

export function shiftPeriodYear(filters: DashboardFiltersValue, offset: number): DashboardFiltersValue {
  return { ...filters, year: filters.year === 'all' ? 'all' : filters.year + offset,
    startDate: shiftDateYear(filters.startDate, offset), endDate: shiftDateYear(filters.endDate, offset) }
}

export function isFullYearPeriod(filters: DashboardFiltersValue) {
  if (filters.year === 'all' || filters.month !== 'all') return false
  if (!filters.startDate && !filters.endDate) return true
  return (filters.resolution !== '3h' && filters.resolution !== 'hourly')
    && filters.startDate === `${filters.year}-01-01`
    && filters.endDate === `${filters.year}-12-31`
}

function hasMetric(data: DashboardData | null, key: Pollutant) {
  if (data?.metadata?.publishedTimelineId || data?.metadata?.publishedReleaseId) {
    return key === 'aqi' || Boolean(data.metadata.metrics[key])
  }
  return Boolean(data?.metadata?.metrics[key] || data?.dashboardTrendRecords.some((row) => isNumber(row[key])) || data?.provinceSnapshots.some((row) => isNumber(row[key])))
}

/** Primary pollutants never fall back to quantities integrated over the atmosphere. */
export function basicPollutants(data: DashboardData | null): Pollutant[] {
  return BASIC_POLLUTANTS.filter(key => hasMetric(data,key) && data?.metadata?.metrics[key]?.qualityStatus !== 'unavailable')
}

export function metricOptions(data: DashboardData | null, basic = false) {
  const keys: Pollutant[] = basic ? ['aqi', ...BASIC_POLLUTANTS] : ['aqi', ...BASIC_POLLUTANTS, ...(Object.keys(METRIC_META) as Pollutant[]).filter(key => key !== 'aqi' && !BASIC_POLLUTANTS.includes(key))]
  return keys.filter(key => hasMetric(data,key) && data?.metadata?.metrics[key]?.qualityStatus !== 'unavailable')
    .map(value => ({value,label:value === 'aqi' && (data?.metadata?.publishedTimelineId || data?.metadata?.publishedReleaseId) && !data.dashboardTrendRecords.some(row=>isNumber(row.aqi)) && !data.provinceSnapshots.some(row=>isNumber(row.aqi)) ? (data.metadata?.temporalAggregation?.startsWith('monthly_') ? 'AQI · không định nghĩa theo tháng' : 'AQI · chưa đủ dữ liệu hợp lệ') : METRIC_META[value].label,group:metricCategory(value)}))
}

/** Geography keeps all provinces; a province selection scopes the adjoining panels. */
export function periodSnapshots(data: DashboardData | null, filters: DashboardFiltersValue, useSnapshot = false): ProvinceSnapshot[] {
  if (!data) return []
  if (useSnapshot) return data.provinceSnapshots
  const grouped = new Map<string, AdminTrendRecord[]>()
  for (const row of data.dashboardTrendRecords) {
    if (!matchesPeriod(row, filters, false, data.metadata?.temporalAggregation)) continue
    const rows = grouped.get(row.provinceCode) ?? []
    rows.push(row)
    grouped.set(row.provinceCode, rows)
  }
  return data.provinceSnapshots.map((province) => {
    const rows = grouped.get(province.provinceCode) ?? []
    const metrics = Object.fromEntries(Object.keys(METRIC_META).map((key) => [key, weightedMetricMean(rows, key as Pollutant)]))
    return { ...province, ...metrics, aqi: rows.length === 1 ? rows[0].aqi ?? null : null, status: null,
      pm25: metrics.pm25, pm10: metrics.pm10 }
  })
}

export function buildMonitoringView(data: DashboardData | null, filters: DashboardFiltersValue, useSnapshot = false) {
  const snapshots = periodSnapshots(data, filters, useSnapshot)
  const scoped = snapshots.filter((province) => filters.provinceCode === 'all' || province.provinceCode === filters.provinceCode)
  const records = (data?.dashboardTrendRecords ?? []).filter((record) => matchesPeriod(record, filters, true, data?.metadata?.temporalAggregation))
  const groups = new Map<string, Array<{ value: number; weight: number }>>()
  for (const record of records) {
    const value = record[filters.pollutant]
    if (!isNumber(value)) continue
    const date = chartKey(record.date, filters.resolution)
    const values = groups.get(date) ?? []
    values.push({ value, weight: filters.pollutant === 'aqi' ? 1 : record.metricSampleCounts?.[filters.pollutant] ?? 1 })
    groups.set(date, values)
  }
  const metric = { ...METRIC_META[filters.pollutant], ...data?.metadata?.metrics[filters.pollutant] }
  const ranking = scoped.filter((province) => isNumber(province[filters.pollutant])).map((province) => ({
    id: province.provinceCode, label: province.provinceName, value: province[filters.pollutant] as number,
  })).sort((a, b) => b.value - a.value)
  const chartPoints = [...groups].sort(([a], [b]) => a.localeCompare(b)).flatMap(([date, values]) => filters.pollutant === 'aqi' && values.length !== 1 ? [] : [{ label: chartLabel(date, filters.resolution), timestamp: date, value: values.reduce((sum, item) => sum + item.value * item.weight, 0) / values.reduce((sum, item) => sum + item.weight, 0) }])
  if (filters.resolution === 'hourly' || filters.resolution === '3h') {
    const cadence = filters.resolution === 'hourly' ? 3600000 : 10800000
    for (let i = 1; i < chartPoints.length; i++) {
      if (Date.parse(chartPoints[i].timestamp) - Date.parse(chartPoints[i - 1].timestamp) > cadence) Object.assign(chartPoints[i], { breakBefore: true })
    }
  }
  const instant = chartPoints.length === 1 ? chartPoints[0].timestamp : ''
  const bound = filters.resolution === 'monthly' ? `${instant}-01` : instant.slice(0, (filters.resolution === '3h' || filters.resolution === 'hourly') ? 16 : 10)
  return {
    snapshots, records, metric, ranking,
    scopeLabel: filters.provinceCode === 'all' ? 'Toàn quốc' : data?.provinceSnapshots.find((province) => province.provinceCode === filters.provinceCode)?.provinceName ?? filters.provinceCode,
    aqi: scoped.length === 1 ? scoped[0].aqi : null,
    metrics: Object.fromEntries(Object.keys(METRIC_META).map((key) => [key, key === 'aqi' ? (scoped.length === 1 ? scoped[0].aqi : null) : data?.metadata?.publishedReleaseId || data?.metadata?.cadenceHours ? weightedMetricMean(records, key as Pollutant) : mean(scoped.map((province) => province[key as Pollutant]))])) as Record<Pollutant, number | null>,
    reportingProvinces: ranking.length,
    chartPoints,
    observationContext: instant ? observationContext(periodSnapshots(data, { ...filters, year: 'all', month: 'all', startDate: bound, endDate: bound }), filters.pollutant, filters.provinceCode) : undefined,
  }
}

export function periodLabel(filters: DashboardFiltersValue, timezone = 'UTC') {
  const zone = filters.resolution === 'hourly' || filters.resolution === '3h' ? 'UTC+7' : timezone === 'Asia/Ho_Chi_Minh' ? 'UTC+7' : timezone
  if (filters.startDate || filters.endDate) return `${formatDateTime(filters.startDate) || 'Đầu chuỗi'}${filters.startDate === filters.endDate ? '' : ` → ${formatDateTime(filters.endDate) || 'Cuối chuỗi'}`} ${zone}`
  return [filters.month === 'all' ? null : `Tháng ${filters.month}`, filters.year === 'all' ? 'Toàn bộ thời gian' : `Năm ${filters.year}`].filter(Boolean).join(' · ')
}
