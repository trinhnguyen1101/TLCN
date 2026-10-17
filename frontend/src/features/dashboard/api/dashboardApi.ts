import type { DashboardData } from '../types'
import { createDashboardLoader, type LoadOptions } from './dashboardTransport'

const load = createDashboardLoader('/api/dashboard', (raw) => raw as DashboardData,
  'Không thể tải dữ liệu theo dõi. Vui lòng kiểm tra kết nối và thử lại.')

/** Share one snapshot across consumers and React StrictMode effect remounts. */
export function loadDashboardData(query = 'resolution=3h', options?: LoadOptions): Promise<DashboardData> {
  return load(query, options)
}
