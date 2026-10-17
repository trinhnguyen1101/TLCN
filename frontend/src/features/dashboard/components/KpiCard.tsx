import { DashboardIcon } from '../../../components/ui/DashboardIcon'
import { Skeleton } from '../../../components/ui/Skeleton'

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
  return <article className={`flex min-w-0 flex-col gap-2 rounded-card border p-4 shadow-card ${tone === 'yellow' ? 'border-highlight-border bg-highlight-soft' : tone === 'red' ? 'border-danger/25 bg-danger-soft' : 'border-border bg-surface'}`}>
    <div className="flex items-start justify-between gap-2 text-xs text-secondary"><span className="min-w-0 wrap-anywhere">{label}</span><span className={`shrink-0 rounded-lg p-1.5 ${tone === 'yellow' ? 'bg-highlight/10 text-highlight' : tone === 'red' ? 'bg-danger/10 text-danger' : 'bg-accent-soft text-accent'}`}><DashboardIcon name={icon} size="small" /></span></div>
    {loading ? <Skeleton className="my-1 h-7 w-24" /> : <strong className="my-1 text-[clamp(1rem,1.3vw,1.45rem)] font-semibold text-heading tabular-nums wrap-anywhere" style={{ color: valueColor }}>{value}</strong>}
    <span className={`mt-auto text-[.7rem] wrap-anywhere ${trend === 'up' ? 'text-danger' : trend === 'down' ? 'text-success' : 'text-muted'}`}>{detail}</span>
  </article>
}
