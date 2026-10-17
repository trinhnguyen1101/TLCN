import type { AdminDashboardData } from '../types'
import { createDashboardLoader, type LoadOptions } from './dashboardTransport'

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const isString = (value: unknown): value is string => typeof value === 'string'
const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

const load = createDashboardLoader<AdminDashboardData>('/api/admin/dashboard', (payload: unknown) => {
  if (!isObject(payload)) throw new Error('Nguồn dữ liệu quản lý trả về phản hồi không hợp lệ. Vui lòng thử lại.')
  const raw = payload as Partial<AdminDashboardData>
  return {
    provinceSnapshots: Array.isArray(raw.provinceSnapshots) ? raw.provinceSnapshots.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName)) : [],
    emissionRecords: Array.isArray(raw.emissionRecords) ? raw.emissionRecords.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName) && isString(row.sector) && isFiniteNumber(row.year) && isFiniteNumber(row.month)) : [],
    emissionSectors: Array.isArray(raw.emissionSectors) ? raw.emissionSectors.filter(isString) : [],
    dashboardTrendRecords: Array.isArray(raw.dashboardTrendRecords) ? raw.dashboardTrendRecords.filter((row) => isObject(row) && isString(row.provinceCode) && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00))?$/.test(String(row.date))) : [],
    priorityAreas: Array.isArray(raw.priorityAreas) ? raw.priorityAreas.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName)) : [],
    annualProvinceSummaries: Array.isArray(raw.annualProvinceSummaries) ? raw.annualProvinceSummaries.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName) && isFiniteNumber(row.year)) : [],
    metadata: raw.metadata ?? null,
  }
}, 'Không thể tải dữ liệu quản lý. Vui lòng kiểm tra kết nối và thử lại.')

export function loadAdminDashboardData(query = 'resolution=3h', options?: LoadOptions): Promise<AdminDashboardData> {
  return load(query, options)
}
