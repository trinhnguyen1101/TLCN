import { useEffect, useState } from 'react'
import type { DashboardAnalytics, DashboardFiltersValue } from '../types/dashboard'

export function useDashboardAnalytics(filters: DashboardFiltersValue, enabled: boolean, generation?: string) {
  const params = new URLSearchParams({ provinceCode: filters.provinceCode, metric: filters.pollutant })
  if (filters.year !== 'all') params.set('year', String(filters.year))
  if (filters.month !== 'all') params.set('month', String(filters.month))
  if (filters.startDate) params.set('startDate', filters.startDate)
  if (filters.endDate) params.set('endDate', filters.endDate)
  const query = params.toString()
  const key = `${generation ?? ''}:${query}`
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{ key: string; data: DashboardAnalytics | null; error: string | null }>({
    key: '',
    data: null,
    error: null,
  })
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      fetch(`/api/dashboard/analytics?${query}`, {
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      })
        .then(async (response) => {
          if (!response.ok) throw new Error(String(response.status))
          return (await response.json()) as DashboardAnalytics
        })
        .then((data) => {
          if (generation && data.generation !== generation) throw new Error('Dashboard generation changed during analytics request')
          if (!controller.signal.aborted) setState({ key, data, error: null })
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted)
            setState((current) => ({
              key,
              data: current.data,
              error: error instanceof Error && error.message.includes('generation')
                ? 'Nguồn dữ liệu đã đổi trong lúc tải phân tích. Hãy tải lại dashboard để đồng bộ.'
                : 'Không tải được phân tích. Hãy kiểm tra khoảng ngày và thử lại.',
            }))
        })
    }, 180)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [enabled, query, key, generation, attempt])
  const current = enabled && state.key === key
  return {
    data: enabled ? state.data : null,
    error: current ? state.error : null,
    loading: enabled && (!current || (!state.data && !state.error)),
    retry: () => {
      setState({ key: '', data: null, error: null })
      setAttempt((value) => value + 1)
    },
  }
}
