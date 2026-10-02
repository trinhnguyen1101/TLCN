import { DashboardIcon } from './DashboardIcon'
import { Skeleton } from '../ui/Skeleton'

interface KpiCardProps {
  label: string
  value: string
  detail: string
  icon?: 'air' | 'location' | 'chart' | 'emission' | 'layers'
  tone?: 'paper' | 'yellow' | 'red'
  trend?: 'up' | 'down' | 'neutral'
  valueColor?: string
  loading?: boolean
}
export function KpiCard({ label, value, detail, icon = 'chart', tone = 'paper', trend, valueColor, loading }: KpiCardProps) {
  return <article className={`flex min-w-0 flex-col gap-2 rounded-card border p-4 ${tone === 'yellow' ? 'border-accent-border bg-accent-soft' : 'border-border bg-surface'}`}>
    <div className="flex items-start justify-between gap-2 text-xs text-muted"><span>{label}</span><DashboardIcon name={icon} size="small" /></div>
    {loading ? <Skeleton className="my-1 h-7 w-24" /> : <strong className="my-1 text-[clamp(1rem,1.3vw,1.45rem)] font-semibold text-heading tabular-nums wrap-anywhere" style={{ color: valueColor }}>{value}</strong>}
    <span className={`mt-auto text-[.7rem] ${trend === 'up' ? 'text-danger' : trend === 'down' ? 'text-success' : 'text-muted'}`}>{detail}</span>
  </article>
}
