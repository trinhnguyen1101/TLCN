import type { DashboardFiltersValue } from '../types'

export const GOLD_DASHBOARD = import.meta.env?.VITE_DASHBOARD_SOURCE === 'gold'
export const DEFAULT_RESOLUTION: DashboardFiltersValue['resolution'] = 'hourly'
export const RESOLUTION_OPTIONS = [
  { value: 'hourly' as const, label: '1 giờ' },
  { value: 'daily' as const, label: 'Ngày' }, { value: 'monthly' as const, label: 'Tháng' },
]
