import { loadDashboardData } from '../api/dashboardApi'
import { useTemporalData } from './useTemporalData'

export function useDashboardData(query = 'resolution=3h', comparisonYear?: number) {
  return useTemporalData(loadDashboardData, query, comparisonYear, true, comparisonYear !== undefined)
}
