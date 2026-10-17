import { useEffect, useState } from 'react'
import type { DashboardData } from '../types'
import type { DashboardLoader } from '../api/dashboardTransport'
import { withComparison } from '../model/temporal'

export function useTemporalData<T extends DashboardData>(load: DashboardLoader<T>, query: string, comparisonYear?: number, enabled = true, includeComparison = true) {
  const key = `${query}|${includeComparison ? comparisonYear ?? 'previous' : 'primary'}`
  const [state, setState] = useState<{ key: string; data: T | null; error: string | null; comparing: boolean; comparisonError: string | null }>({ key: '', data: null, error: null, comparing: false, comparisonError: null })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const request = (next: string) => load(next, { signal: controller.signal, force: attempt > 0 })
    request(query).then(async (data) => {
      if (controller.signal.aborted) return
      setState({ key, data, error: null, comparing: includeComparison, comparisonError: null })
      if (!includeComparison) return
      try {
        const compared = await withComparison(data, request, new URLSearchParams(query).get('resolution') ?? '3h', comparisonYear)
        if (!controller.signal.aborted) setState({ key, data: compared, error: null, comparing: false, comparisonError: null })
      } catch (error: unknown) {
        if (!controller.signal.aborted) setState({ key, data, error: null, comparing: false, comparisonError: error instanceof Error ? error.message : 'Không thể tải kỳ so sánh.' })
      }
    }, (error: unknown) => {
      if (!controller.signal.aborted) setState((previous) => ({ ...previous, key, error: error instanceof Error ? error.message : 'Không thể tải dữ liệu.', comparing: false }))
    })
    return () => controller.abort()
  }, [load, query, comparisonYear, key, attempt, enabled, includeComparison])
  return { data: enabled ? state.data : null, loading: enabled && state.key !== key, error: enabled && state.key === key ? state.error : null,
    comparisonLoading: enabled && state.key === key && state.comparing, comparisonError: enabled && state.key === key ? state.comparisonError : null,
    retry: () => { setState((previous) => ({ ...previous, key: '', error: null })); setAttempt((value) => value + 1) } }
}
