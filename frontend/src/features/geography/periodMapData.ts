import type { DashboardData, DashboardFiltersValue, ProvinceSnapshot } from '../../types/dashboard'

type PeriodFilters = Pick<DashboardFiltersValue, 'year' | 'month' | 'startDate' | 'endDate'>
type MapSource = Pick<DashboardData, 'provinceSnapshots' | 'dashboardTrendRecords'>
const METRICS = ['pm1', 'pm25', 'pm10'] as const

/** The map uses already-loaded monthly records, independently of the analytics request. */
export function buildPeriodMapSnapshots(data: MapSource | null, filters: PeriodFilters): ProvinceSnapshot[] {
  if (!data) return []
  const monthsByProvince = new Map<string, Map<string, Record<(typeof METRICS)[number], number[]>>>()
  const invalidPeriod = Boolean(filters.startDate && filters.endDate && filters.startDate > filters.endDate)
  for (const record of data.dashboardTrendRecords) {
    if (invalidPeriod) continue
    const month = record.date.slice(0, 7)
    if (filters.year !== 'all' && Number(month.slice(0, 4)) !== filters.year) continue
    if (filters.month !== 'all' && Number(month.slice(5, 7)) !== filters.month) continue
    if (filters.startDate && month < filters.startDate.slice(0, 7)) continue
    if (filters.endDate && month > filters.endDate.slice(0, 7)) continue
    let province = monthsByProvince.get(record.provinceCode)
    if (!province) {
      province = new Map()
      monthsByProvince.set(record.provinceCode, province)
    }
    let values = province.get(month)
    if (!values) {
      values = { pm1: [], pm25: [], pm10: [] }
      province.set(month, values)
    }
    for (const metric of METRICS) {
      const value = record[metric]
      if (typeof value === 'number' && Number.isFinite(value)) values[metric].push(value)
    }
  }
  const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length
  return data.provinceSnapshots.map((province) => {
    const snapshot: ProvinceSnapshot = {
      ...province,
      aqi: null,
      status: null,
      pm1: null,
      pm25: null,
      pm10: null,
    }
    for (const metric of METRICS) {
      const monthlyMeans = [...(monthsByProvince.get(province.provinceCode)?.values() ?? [])]
        .filter((values) => values[metric].length)
        .map((values) => mean(values[metric]))
      snapshot[metric] = monthlyMeans.length ? mean(monthlyMeans) : null
    }
    return snapshot
  })
}
