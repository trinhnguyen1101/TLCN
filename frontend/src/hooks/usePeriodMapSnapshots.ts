import { useMemo } from 'react'
import type { DashboardData, DashboardFiltersValue } from '../types/dashboard'
import { buildPeriodMapSnapshots } from '../features/geography/periodMapData'

export function usePeriodMapSnapshots(data: DashboardData | null, filters: DashboardFiltersValue) {
  const { year, month, startDate, endDate } = filters
  return useMemo(
    () => buildPeriodMapSnapshots(data, { year, month, startDate, endDate }),
    [data, year, month, startDate, endDate],
  )
}
