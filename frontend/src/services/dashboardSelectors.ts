import type { AdminTrendRecord, DashboardData, DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../types/dashboard'

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
export const BASIC_POLLUTANTS: Pollutant[] = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3']
export const DEFAULT_FILTERS: DashboardFiltersValue = {
  provinceCode: 'all', pollutant: 'pm25', year: 'all', month: 'all', startDate: '', endDate: '', sector: 'all',
}
export const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)
export const mean = (values: Array<number | null | undefined>) => {
  const valid = values.filter(isNumber)
  return valid.length ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null
}
export const hasPeriodFilter = (filters: DashboardFiltersValue) => filters.year !== 'all' || filters.month !== 'all' || Boolean(filters.startDate || filters.endDate)

export function matchesPeriod(record: { date: string; provinceCode: string }, filters: DashboardFiltersValue, includeProvince = true) {
  return (!includeProvince || filters.provinceCode === 'all' || record.provinceCode === filters.provinceCode)
    && (filters.year === 'all' || Number(record.date.slice(0, 4)) === filters.year)
    && (filters.month === 'all' || Number(record.date.slice(5, 7)) === filters.month)
    && (!filters.startDate || record.date >= filters.startDate)
    && (!filters.endDate || record.date <= filters.endDate)
}

export function metricOptions(data: DashboardData | null, basic = false) {
  const keys = basic ? ['aqi', ...BASIC_POLLUTANTS] as Pollutant[] : Object.keys(METRIC_META) as Pollutant[]
  return keys.filter((key) => data?.metadata?.metrics[key] || data?.dashboardTrendRecords.some((row) => isNumber(row[key])) || data?.provinceSnapshots.some((row) => isNumber(row[key])))
    .map((value) => ({ value, label: METRIC_META[value].label }))
}

/** Geography keeps all provinces; a province selection scopes the adjoining panels. */
export function periodSnapshots(data: DashboardData | null, filters: DashboardFiltersValue, useSnapshot = false): ProvinceSnapshot[] {
  if (!data) return []
  if (useSnapshot) return data.provinceSnapshots
  const grouped = new Map<string, AdminTrendRecord[]>()
  for (const row of data.dashboardTrendRecords) {
    if (!matchesPeriod(row, filters, false)) continue
    const rows = grouped.get(row.provinceCode) ?? []
    rows.push(row)
    grouped.set(row.provinceCode, rows)
  }
  return data.provinceSnapshots.map((province) => {
    const rows = grouped.get(province.provinceCode) ?? []
    const metrics = Object.fromEntries(Object.keys(METRIC_META).map((key) => [key, mean(rows.map((row) => row[key as Pollutant]))]))
    return { ...province, ...metrics, aqi: mean(rows.map((row) => row.aqi)), status: null,
      pm25: metrics.pm25, pm10: metrics.pm10 }
  })
}

export function buildMonitoringView(data: DashboardData | null, filters: DashboardFiltersValue, useSnapshot = false) {
  const snapshots = periodSnapshots(data, filters, useSnapshot)
  const scoped = snapshots.filter((province) => filters.provinceCode === 'all' || province.provinceCode === filters.provinceCode)
  const records = (data?.dashboardTrendRecords ?? []).filter((record) => matchesPeriod(record, filters))
  const groups = new Map<string, number[]>()
  for (const record of records) {
    const value = record[filters.pollutant]
    if (!isNumber(value)) continue
    const date = record.date.slice(0, 7)
    const values = groups.get(date) ?? []
    values.push(value)
    groups.set(date, values)
  }
  const metric = { ...METRIC_META[filters.pollutant], ...data?.metadata?.metrics[filters.pollutant] }
  const ranking = scoped.filter((province) => isNumber(province[filters.pollutant])).map((province) => ({
    id: province.provinceCode, label: province.provinceName, value: province[filters.pollutant] as number,
  })).sort((a, b) => b.value - a.value)
  return {
    snapshots, records, metric, ranking,
    scopeLabel: filters.provinceCode === 'all' ? 'Toàn quốc' : data?.provinceSnapshots.find((province) => province.provinceCode === filters.provinceCode)?.provinceName ?? filters.provinceCode,
    aqi: mean(scoped.map((province) => province.aqi)),
    metrics: Object.fromEntries(Object.keys(METRIC_META).map((key) => [key, mean(scoped.map((province) => province[key as Pollutant]))])) as Record<Pollutant, number | null>,
    reportingProvinces: ranking.length,
    chartPoints: [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([date, values]) => ({ label: `${date.slice(5)}/${date.slice(0, 4)}`, value: Number(mean(values)!.toFixed(metric.unit === '1' ? 3 : 2)) })),
  }
}

export function periodLabel(filters: DashboardFiltersValue) {
  if (filters.startDate || filters.endDate) return `${filters.startDate || 'Đầu chuỗi'} → ${filters.endDate || 'Cuối chuỗi'}`
  return [filters.month === 'all' ? null : `Tháng ${filters.month}`, filters.year === 'all' ? 'Toàn bộ thời gian' : `Năm ${filters.year}`].filter(Boolean).join(' · ')
}
