import type { DashboardData, DashboardFiltersValue } from '../types'
import { isNumber, matchesPeriod } from './dashboardSelectors'

export function dataQuality(data: DashboardData | null, filters: DashboardFiltersValue) {
  const rows = (data?.dashboardTrendRecords ?? []).filter(row => matchesPeriod(row, filters, true, data?.metadata?.temporalAggregation))
  let valid = rows.filter(row => isNumber(row[filters.pollutant])).length
  const hourly = filters.resolution === 'hourly' || filters.resolution === '3h'
  const start = filters.startDate || data?.metadata?.queryStart || ''
  const end = filters.endDate || data?.metadata?.queryEnd || ''
  const instant = (value: string) => Date.parse(value.length === 10 ? `${value}T00:00:00Z` : /[Zz]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`)
  const first = instant(start), last = instant(end)
  const provinces = filters.provinceCode === 'all' ? data?.provinceSnapshots.length ?? 0 : 1
  const cadence = filters.resolution === '3h' ? 3 : data?.metadata?.cadenceHours ?? 1
  let expected = hourly && Number.isFinite(first) && Number.isFinite(last)
    ? (Math.floor((last - first) / (cadence * 3600000)) + 1) * provinces : rows.length
  const sourceSamples = !hourly && Boolean(data?.metadata?.cadenceHours)
  if (sourceSamples && Number.isFinite(first) && Number.isFinite(last)) {
    valid = rows.reduce((sum, row) => sum + (row.metricSampleCounts?.[filters.pollutant] ?? 0), 0)
    if (filters.resolution === 'monthly') {
      let days = 0
      const firstDate = new Date(first), lastDate = new Date(last)
      for (let index = firstDate.getUTCFullYear() * 12 + firstDate.getUTCMonth(); index <= lastDate.getUTCFullYear() * 12 + lastDate.getUTCMonth(); index++) {
        days += new Date(Date.UTC(Math.floor(index / 12), index % 12 + 1, 0)).getUTCDate()
      }
      expected = days * (24 / cadence) * provinces
    } else {
      const firstDay = Math.floor(first / 86400000), lastDay = Math.floor(last / 86400000)
      expected = (lastDay - firstDay + 1) * (24 / cadence) * provinces
    }
  }
  return { rows, valid, expected, missing: Math.max(0, expected - valid), coverage: expected ? valid / expected : null, hourly, sourceSamples }
}
