import { useEffect, useState } from 'react'
import { loadDashboardData } from '../services/dashboardApi'
import type { DashboardData } from '../types/dashboard'

type DashboardState =
  | { data: null; loading: true; error: null }
  | { data: null; loading: false; error: string }
  | { data: DashboardData; loading: false; error: null }

export function useDashboardData() {
  const [state, setState] = useState<DashboardState>({ data: null, loading: true, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    loadDashboardData().then(
      (data) => { if (active) setState({ data, loading: false, error: null }) },
      () => {
        if (active) setState({ data: null, loading: false, error: 'Không thể tải dữ liệu dashboard. Vui lòng kiểm tra kết nối và thử lại.' })
      },
    )
    return () => { active = false }
  }, [attempt])

  const retry = () => {
    setState({ data: null, loading: true, error: null })
    setAttempt((current) => current + 1)
  }

  return { ...state, retry }
}
