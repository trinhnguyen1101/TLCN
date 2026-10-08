import type { DashboardData, DashboardFiltersValue, DashboardMetadata } from '../types'
import { formatDate, formatDateTime } from '../../../utils/dates'

export function temporalQuery(filters: Partial<DashboardFiltersValue>) {
  const params = new URLSearchParams({ resolution: filters.resolution ?? '3h' })
  if (filters.startDate) params.set('start', filters.startDate)
  if (filters.endDate) params.set('end', filters.endDate)
  return params.toString()
}

export function periodYears(metadata: DashboardMetadata | null | undefined, fallback: number[], resolution: DashboardFiltersValue['resolution']) {
  if (resolution === 'monthly') return metadata?.availableYears?.length ? metadata.availableYears : fallback
  const start = Number((metadata?.observationStart ?? metadata?.start)?.slice(0, 4))
  const end = Number((metadata?.observationEnd ?? metadata?.end)?.slice(0, 4))
  return Number.isFinite(start) && Number.isFinite(end)
    ? Array.from({ length: end - start + 1 }, (_, index) => end - index) : fallback
}

export function inputInstant(value?: string | null) {
  return value?.slice(0, 16) ?? ''
}

export function periodDefaults(metadata?: DashboardMetadata | null, resolution: DashboardFiltersValue['resolution'] = '3h') {
  const size = resolution === '3h' ? 16 : 10
  return { startDate: metadata?.queryStart?.slice(0, size) ?? '', endDate: metadata?.queryEnd?.slice(0, size) ?? '' }
}

export function calendarPeriod(filters: DashboardFiltersValue, years: number[], year: number | 'all', month: number | 'all'): DashboardFiltersValue {
  if (year === 'all' && month === 'all') return { ...filters, year, month, startDate: '', endDate: '' }
  const selectedYear = year === 'all' ? Number(filters.endDate.slice(0, 4)) || years[0] : year
  if (!selectedYear) return filters
  const selectedMonth = month === 'all' ? (filters.resolution === '3h' ? Number(filters.endDate.slice(5, 7)) || 1 : 1) : month
  const endMonth = month === 'all' && filters.resolution !== '3h' ? 12 : selectedMonth
  const start = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}-01`
  const end = `${selectedYear}-${String(endMonth).padStart(2, '0')}-${new Date(Date.UTC(selectedYear, endMonth, 0)).getUTCDate()}`
  return { ...filters, year: selectedYear, month,
    startDate: filters.resolution === '3h' ? `${start}T00:00` : start,
    endDate: filters.resolution === '3h' ? `${end}T21:00` : end }
}

export function trendDescription(resolution: DashboardFiltersValue['resolution']) {
  return resolution === '3h' ? 'Số liệu mỗi 3 giờ theo giờ quốc tế (UTC). Giá trị toàn quốc là trung bình các tỉnh, thành phố có dữ liệu tại cùng thời điểm.'
    : `Giá trị trung bình theo ${resolution === 'daily' ? 'ngày' : 'tháng'} trong phạm vi đang chọn.`
}

export function chartKey(date: string, resolution: DashboardFiltersValue['resolution']) {
  return resolution === 'monthly' ? date.slice(0, 7) : resolution === 'daily' ? date.slice(0, 10) : date
}

export function chartLabel(date: string, resolution: DashboardFiltersValue['resolution']) {
  if (resolution === 'monthly') return `${date.slice(5, 7)}/${date.slice(0, 4)}`
  return resolution === 'daily' ? formatDate(date) : formatDateTime(date)
}

export function inDateRange(date: string, start: string, end: string, resolution: DashboardFiltersValue['resolution']) {
  // Aggregate rows represent calendar periods, not instants on the first day.
  if (resolution !== '3h') {
    const size = resolution === 'monthly' ? 7 : 10
    return (!start || date.slice(0, size) >= start.slice(0, size)) && (!end || date.slice(0, size) <= end.slice(0, size))
  }
  const time = Date.parse(date.length === 10 ? `${date}T00:00:00Z` : date)
  const bound = (value: string, isEnd: boolean) => Date.parse(value.length === 10
    ? `${value}T${isEnd ? '23:59:59.999' : '00:00:00'}Z` : `${value.replace(/Z$/, '')}Z`)
  return (!start || time >= bound(start, false)) && (!end || time <= bound(end, true))
}

export function alignYear(value: string, year: number) {
  if (!value) return ''
  const date = `${year}${value.slice(4)}`
  // February 29 maps to February 28 in a non-leap comparison year.
  return date.slice(5, 10) === '02-29' && new Date(Date.UTC(year, 2, 0)).getUTCDate() === 28
    ? `${date.slice(0, 8)}28${date.slice(10)}` : date
}

export function comparisonBounds(start: string, end: string, year: number) {
  const referenceYear = Number(end.slice(0, 4))
  return { start: alignYear(start, Number(start.slice(0, 4)) + year - referenceYear), end: alignYear(end, year) }
}

export function comparisonFilters(filters: DashboardFiltersValue, year: number): DashboardFiltersValue {
  if (filters.startDate && filters.endDate) {
    const bounds = comparisonBounds(filters.startDate, filters.endDate, year)
    return { ...filters, year: 'all', startDate: bounds.start, endDate: bounds.end }
  }
  return { ...filters, year, startDate: alignYear(filters.startDate, year), endDate: alignYear(filters.endDate, year) }
}

export async function withComparison<T extends DashboardData>(
  data: T, load: (query: string) => Promise<T>, resolution: string, comparisonYear?: number,
): Promise<T> {
  if (!data.metadata?.queryStart || !data.metadata.queryEnd) return data
  if (resolution === 'monthly' && data.metadata.queryStart.slice(0, 4) !== data.metadata.queryEnd.slice(0, 4)) return data
  const year = comparisonYear ?? Number(data.metadata.queryEnd.slice(0, 4)) - 1
  if (year === Number(data.metadata.queryEnd.slice(0, 4))) return data
  const bounds = comparisonBounds(inputInstant(data.metadata.queryStart), inputInstant(data.metadata.queryEnd), year)
  const sourceStart = resolution === 'monthly' ? data.metadata.start : data.metadata.observationStart
  const sourceEnd = resolution === 'monthly' ? data.metadata.end : data.metadata.observationEnd
  if (sourceStart && bounds.end < sourceStart.slice(0, 16)
    || sourceEnd && bounds.start > sourceEnd.slice(0, 16)) {
    return { ...data, comparisonTrendRecords: [] }
  }
  const params = new URLSearchParams({ resolution, ...bounds })
  const comparison = await load(params.toString())
  if (comparison.metadata?.generation !== data.metadata.generation) throw new Error('Bộ dữ liệu đã thay đổi. Vui lòng tải lại để so sánh cùng nguồn.')
  return { ...data, comparisonTrendRecords: comparison.dashboardTrendRecords }
}
