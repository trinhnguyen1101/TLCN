import { loadAdminDashboardData } from '../api/adminDashboardApi'
import { useTemporalData } from './useTemporalData'

export function useAdminDashboardData(query = 'resolution=3h') {
  return useTemporalData(loadAdminDashboardData, query)
}
