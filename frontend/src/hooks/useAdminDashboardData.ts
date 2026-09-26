import { useEffect, useState } from 'react'
import { loadAdminDashboardData } from '../services/adminDashboardApi'
import type { AdminDashboardData } from '../types/dashboard'

type DashboardState =
  | { data: null; loading: true; error: null }
  | { data: null; loading: false; error: string }
  | { data: AdminDashboardData; loading: false; error: null }

export function useAdminDashboardData() {
  const [state, setState] = useState<DashboardState>({ data: null, loading: true, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    loadAdminDashboardData().then(
      (data) => { if (active) setState({ data, loading: false, error: null }) },
      () => { if (active) setState({ data: null, loading: false, error: 'Không thể tải dữ liệu quản lý. Vui lòng kiểm tra kết nối và thử lại.' }) },
    )
    return () => { active = false }
  }, [attempt])

  const retry = () => {
    setState({ data: null, loading: true, error: null })
    setAttempt((current) => current + 1)
  }

  return { ...state, retry }
}
