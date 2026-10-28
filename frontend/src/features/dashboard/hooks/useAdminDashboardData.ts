import { DEFAULT_RESOLUTION } from '../model/resolution'
import { loadAdminDashboardData } from '../api/adminDashboardApi'
import { useTemporalData } from './useTemporalData'

export function useAdminDashboardData(query = `resolution=${DEFAULT_RESOLUTION}`) {
  return useTemporalData(loadAdminDashboardData, query)
}
