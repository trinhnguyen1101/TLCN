import type { ReactNode } from 'react'

interface DataStateProps {
  loading?: boolean
  error?: string | null
  isEmpty?: boolean
  emptyMessage?: string
  children: ReactNode
  className?: string
  compact?: boolean
}

export function DataState({ loading = false, error = null, isEmpty = false, emptyMessage = 'Chưa có dữ liệu theo bộ lọc.', children, className = '', compact = false }: DataStateProps) {
  const classes = `grid place-content-center justify-items-center gap-2.5 px-6 py-8 text-center text-[.83rem] leading-[1.6] ${compact ? 'min-h-50' : 'min-h-60'} ${className}`
  if (loading) return <div className={`${classes} text-muted`} role="status"><span className="size-[26px] animate-spin rounded-full border-2 border-accent-border border-t-accent [animation-duration:.8s] motion-reduce:animate-none" />Đang tải dữ liệu…</div>
  if (error) return <div className={`${classes} text-danger`} role="alert">{error}</div>
  if (isEmpty) return <div className={`${classes} text-muted`}><strong className="text-[.94rem] font-medium text-ink">Chưa có dữ liệu</strong><span>{emptyMessage}</span></div>
  return <>{children}</>
}
