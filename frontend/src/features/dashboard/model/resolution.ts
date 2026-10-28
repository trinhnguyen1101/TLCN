import type { DashboardFiltersValue } from '../types'

export const GOLD_DASHBOARD = import.meta.env?.VITE_DASHBOARD_SOURCE === 'gold'
export const DEFAULT_RESOLUTION: DashboardFiltersValue['resolution'] = GOLD_DASHBOARD ? 'hourly' : '3h'
export const RESOLUTION_OPTIONS = [
  ...(GOLD_DASHBOARD ? [{ value: 'hourly' as const, label: '1 giờ' }] : [{ value: '3h' as const, label: '3 giờ' }]),
  { value: 'daily' as const, label: 'Ngày' }, { value: 'monthly' as const, label: 'Tháng' },
]
