import type { DashboardData } from '../types/dashboard'

let dashboardRequest: Promise<DashboardData> | undefined

/** Share one snapshot across consumers and React StrictMode effect remounts. */
export function loadDashboardData(): Promise<DashboardData> {
  dashboardRequest ??= fetch('/api/dashboard', { signal: AbortSignal.timeout(15_000) })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Dashboard API: HTTP ${response.status}`)
      return await response.json() as DashboardData
    })
    .catch((error: unknown) => {
      // A failed request must not prevent a subsequent retry.
      dashboardRequest = undefined
      throw error
    })
  return dashboardRequest
}
