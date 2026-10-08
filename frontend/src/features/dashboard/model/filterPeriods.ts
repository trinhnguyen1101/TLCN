import type { DashboardFiltersValue, DashboardMetadata } from '../types'
import { formatDate, formatDateTime } from '../../../utils/dates'

type Resolution = DashboardFiltersValue['resolution']
export type PeriodPreset = 'latest' | '7d' | '30d' | 'month' | 'year' | 'history'
const DAY = 86_400_000
const instant = (value: string) => Date.parse(`${value.slice(0, 19)}${value.length === 10 ? 'T00:00:00' : ''}Z`)
const dateString = (date: Date) => date.toISOString().slice(0, 10)

/** A changed period must submit both bounds, even when one matches a displayed default. */
export function mergeFilterSelection(previous: Partial<DashboardFiltersValue>, next: DashboardFiltersValue, displayed: DashboardFiltersValue): Partial<DashboardFiltersValue> {
  const periodChanged = (['resolution', 'year', 'month', 'startDate', 'endDate'] as const).some((key) => next[key] !== displayed[key])
  return periodChanged ? next : { ...next, startDate: previous.startDate, endDate: previous.endDate }
}

export function sourceBounds(metadata: DashboardMetadata | null | undefined, resolution: Resolution) {
  return { start: (resolution === 'monthly' ? metadata?.start : metadata?.observationStart ?? metadata?.start) ?? '',
    end: (resolution === 'monthly' ? metadata?.end : metadata?.observationEnd ?? metadata?.end) ?? '' }
}

export function presetPeriod(filters: DashboardFiltersValue, preset: PeriodPreset, metadata?: DashboardMetadata | null): DashboardFiltersValue {
  const base: DashboardFiltersValue = { ...filters, year: 'all', month: 'all' }
  if (preset === 'latest') return { ...base, startDate: '', endDate: '' }
  const bounds = sourceBounds(metadata, filters.resolution)
  const end = new Date(instant(bounds.end || filters.endDate))
  if (!Number.isFinite(end.getTime())) return base
  const start = new Date(end)
  if (preset === 'month') start.setUTCDate(1)
  else if (preset === 'year') { start.setUTCMonth(0, 1); base.year = end.getUTCFullYear() }
  else if (preset === 'history') return { ...base, startDate: bounds.start.slice(0, 10), endDate: bounds.end.slice(0, 10) }
  else start.setTime(end.getTime() - ((preset === '7d' ? 7 : 30) - 1) * DAY)
  const first = bounds.start ? new Date(Math.max(start.getTime(), instant(bounds.start))) : start
  return { ...base, startDate: `${dateString(first)}${filters.resolution === '3h' ? 'T00:00' : ''}`,
    endDate: filters.resolution === '3h' ? end.toISOString().slice(0, 16) : dateString(end) }
}

export function validatePeriod(filters: DashboardFiltersValue, metadata?: DashboardMetadata | null): string | null {
  const { startDate, endDate, resolution } = filters
  if (!startDate && !endDate) return null
  if (!startDate || !endDate) return 'Vui lòng chọn cả ngày bắt đầu và ngày kết thúc.'
  const pattern = resolution === '3h' ? /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/ : /^\d{4}-\d{2}-\d{2}$/
  if (![startDate, endDate].every((value) => pattern.test(value) && Number.isFinite(instant(value))
    && new Date(instant(value)).toISOString().slice(0, value.length) === value)) return 'Ngày hoặc giờ chưa hợp lệ.'
  const start = instant(startDate), end = instant(endDate)
  if (start > end) return 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.'
  if (resolution === '3h' && [startDate, endDate].some((value) => Number(value.slice(11, 13)) % 3 !== 0 || value.slice(14, 16) !== '00')) return 'Chọn giờ quan sát theo UTC: 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00 hoặc 21:00.'
  const limit = resolution === '3h' ? 31 : 366
  if (resolution !== 'monthly' && end - start + (resolution === 'daily' ? DAY - 1 : 0) >= limit * DAY) return `Bạn có thể chọn tối đa ${limit} ngày. ${resolution === '3h' ? 'Chọn chế độ Ngày hoặc Tháng để xem khoảng thời gian dài hơn.' : 'Chọn chế độ Tháng để xem khoảng thời gian dài hơn.'}`
  const bounds = sourceBounds(metadata, resolution)
  const size = resolution === 'monthly' ? 7 : resolution === 'daily' ? 10 : 16
  if (bounds.start && startDate.slice(0, size) < bounds.start.slice(0, size) || bounds.end && endDate.slice(0, size) > bounds.end.slice(0, size)) return 'Khoảng chọn nằm ngoài thời gian có dữ liệu của nguồn.'
  return null
}

export function shiftPeriod(filters: DashboardFiltersValue, direction: -1 | 1, metadata?: DashboardMetadata | null): DashboardFiltersValue | null {
  if (!filters.startDate || !filters.endDate || validatePeriod(filters, metadata)) return null
  const start = new Date(instant(filters.startDate)), end = new Date(instant(filters.endDate))
  if (filters.resolution === 'monthly') {
    const count = (end.getUTCFullYear() - start.getUTCFullYear()) * 12 + end.getUTCMonth() - start.getUTCMonth() + 1
    start.setUTCDate(1); end.setUTCDate(1)
    start.setUTCMonth(start.getUTCMonth() + direction * count)
    end.setUTCMonth(end.getUTCMonth() + direction * count + 1, 0)
  } else {
    const days = Math.floor((end.getTime() - start.getTime()) / DAY) + 1
    start.setTime(start.getTime() + direction * days * DAY)
    end.setTime(end.getTime() + direction * days * DAY)
  }
  const size = filters.resolution === '3h' ? 16 : 10
  const next = { ...filters, year: 'all' as const, month: 'all' as const, startDate: start.toISOString().slice(0, size), endDate: end.toISOString().slice(0, size) }
  return validatePeriod(next, metadata) ? null : next
}

export function shortPeriod(filters: DashboardFiltersValue) {
  if (!filters.startDate && !filters.endDate) return filters.resolution === 'monthly' ? 'Toàn bộ thời gian' : 'Dữ liệu gần nhất'
  const start = filters.startDate, end = filters.endDate
  if (filters.resolution === '3h' && start === end && end.includes('T')) return `${formatDateTime(end)} UTC`
  if (start.slice(0, 10) === end.slice(0, 10)) return formatDate(end)
  return `${formatDate(start)} – ${formatDate(end)}`
}

export function expandTrendPeriod(filters: DashboardFiltersValue, timestamp: string, metadata?: DashboardMetadata | null): DashboardFiltersValue | null {
  const bounds = sourceBounds(metadata, filters.resolution)
  if (!bounds.start || !bounds.end) return null
  const monthly = filters.resolution === 'monthly'
  const point = new Date(instant(timestamp.length === 7 ? `${timestamp}-01` : timestamp))
  if (!Number.isFinite(point.getTime())) return null
  const first = new Date(instant(bounds.start)), last = new Date(instant(bounds.end))
  let start: Date, end: Date
  if (monthly) {
    first.setUTCDate(1); first.setUTCHours(0, 0, 0, 0)
    start = new Date(Math.max(first.getTime(), Date.UTC(point.getUTCFullYear(), point.getUTCMonth() - 11, 1)))
    end = new Date(Math.min(last.getTime(), Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 12, 0)))
  } else {
    point.setUTCHours(0, 0, 0, 0)
    if (filters.resolution === 'daily') { first.setUTCHours(0, 0, 0, 0); last.setUTCHours(0, 0, 0, 0) }
    start = new Date(Math.max(first.getTime(), point.getTime() - 6 * DAY))
    end = new Date(Math.min(last.getTime(), Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() + 6, filters.resolution === '3h' ? 21 : 0)))
  }
  const size = filters.resolution === '3h' ? 16 : 10
  const next: DashboardFiltersValue = { ...filters, year: 'all', month: 'all', startDate: start.toISOString().slice(0, size), endDate: end.toISOString().slice(0, size) }
  return start.getTime() === end.getTime() || validatePeriod(next, metadata) ? null : next
}
