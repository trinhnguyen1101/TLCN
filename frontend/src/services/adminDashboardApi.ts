import type { AdminDashboardData } from '../types/dashboard'

let adminDashboardRequest: Promise<AdminDashboardData> | undefined

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null
const isString = (value: unknown): value is string => typeof value === 'string'
const isFiniteNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value)

export function loadAdminDashboardData(): Promise<AdminDashboardData> {
  adminDashboardRequest ??= fetch('/api/admin/dashboard', { signal: AbortSignal.timeout(15_000) })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Admin dashboard API: HTTP ${response.status}`)
      const payload: unknown = await response.json()
      if (!isObject(payload)) throw new Error('Admin dashboard API: invalid response')
      const raw = payload as Partial<AdminDashboardData>
      return {
        provinceSnapshots: Array.isArray(raw.provinceSnapshots) ? raw.provinceSnapshots.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName)) : [],
        emissionRecords: Array.isArray(raw.emissionRecords) ? raw.emissionRecords.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName) && isString(row.sector) && isFiniteNumber(row.year) && isFiniteNumber(row.month)) : [],
        emissionSectors: Array.isArray(raw.emissionSectors) ? raw.emissionSectors.filter(isString) : [],
        dashboardTrendRecords: Array.isArray(raw.dashboardTrendRecords) ? raw.dashboardTrendRecords.filter((row) => isObject(row) && isString(row.provinceCode) && /^\d{4}-\d{2}-\d{2}$/.test(String(row.date))) : [],
        priorityAreas: Array.isArray(raw.priorityAreas) ? raw.priorityAreas.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName)) : [],
        annualProvinceSummaries: Array.isArray(raw.annualProvinceSummaries) ? raw.annualProvinceSummaries.filter((row) => isObject(row) && isString(row.provinceCode) && isString(row.provinceName) && isFiniteNumber(row.year)) : [],
        metadata: raw.metadata ?? null,
      }
    })
    .catch((error: unknown) => {
      adminDashboardRequest = undefined
      throw error
    })
  return adminDashboardRequest
}
