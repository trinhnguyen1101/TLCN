import { DEFAULT_RESOLUTION } from '../model/resolution'
import { loadDashboardData } from '../api/dashboardApi'
import { useTemporalData } from './useTemporalData'

export function useDashboardData(query = `resolution=${DEFAULT_RESOLUTION}`, comparisonYear?: number) {
  return useTemporalData(loadDashboardData, query, comparisonYear, true, comparisonYear !== undefined)
}
