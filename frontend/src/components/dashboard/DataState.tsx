import type { ReactNode } from 'react'
import './dashboardComponents.css'

interface DataStateProps {
  loading?: boolean
  error?: string | null
  isEmpty?: boolean
  emptyMessage?: string
  children: ReactNode
}

export function DataState({ loading = false, error = null, isEmpty = false, emptyMessage = 'Chưa có dữ liệu theo bộ lọc.', children }: DataStateProps) {
  if (loading) return <div className="data-state" role="status"><span className="spinner" />Đang tải dữ liệu…</div>
  if (error) return <div className="data-state data-state--error" role="alert">{error}</div>
  if (isEmpty) return <div className="data-state"><strong>Chưa có dữ liệu</strong><span>{emptyMessage}</span></div>
  return <>{children}</>
}
