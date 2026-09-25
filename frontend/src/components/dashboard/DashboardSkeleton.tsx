import { Skeleton } from '../ui/Skeleton'

interface DashboardSkeletonProps {
  variant: 'chart' | 'comparison' | 'table'
  loading: boolean
}

/** Layout placeholders only; no sample readings or chart values. */
export function DashboardSkeleton({ variant, loading }: DashboardSkeletonProps) {
  return (
    <div className={variant === 'comparison' ? 'py-2' : 'px-6 pt-2 pb-6 max-[680px]:px-5'} aria-busy={loading}>
      {variant === 'chart' && (
        <div aria-hidden="true" className="grid min-h-48 content-between border-b border-l border-border p-4">
          {[0, 1, 2, 3].map((row) => <Skeleton key={row} animated={loading} className="h-2 w-full" />)}
        </div>
      )}
      {variant === 'comparison' && (
        <div aria-hidden="true" className="grid grid-cols-2 gap-6">
          {[0, 1].map((column) => (
            <div key={column} className="grid gap-3">
              <Skeleton animated={loading} className="h-3 w-24" />
              <Skeleton animated={loading} className="h-8 w-32" />
            </div>
          ))}
          <Skeleton animated={loading} className="col-span-full h-4 w-full" />
        </div>
      )}
      {variant === 'table' && (
        <div aria-hidden="true" className="grid gap-4 py-3">
          {[0, 1, 2, 3].map((row) => (
            <div key={row} className="grid grid-cols-3 gap-6 border-b border-border pb-4 last:border-0">
              <Skeleton animated={loading} className="h-4 w-32" />
              <Skeleton animated={loading} className="h-4 w-28" />
              <Skeleton animated={loading} className="h-4 w-20 justify-self-end" />
            </div>
          ))}
        </div>
      )}
      <p className="mt-4 text-[.78rem] text-muted">{loading ? 'Đang tải số liệu…' : 'Chưa tải được số liệu.'}</p>
    </div>
  )
}
