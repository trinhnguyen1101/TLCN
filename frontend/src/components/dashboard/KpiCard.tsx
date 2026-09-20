interface KpiCardProps {
  label: string
  value: string
  detail: string
  tone?: 'paper' | 'yellow' | 'red'
  trend?: 'up' | 'down' | 'neutral'
}

export function KpiCard({ label, value, detail, tone = 'paper', trend }: KpiCardProps) {
  return (
    <article className={`kpi-card kpi-card--${tone}`}>
      <span className="kpi-card__label">{label}</span>
      <strong className="kpi-card__value">{value}</strong>
      <span className={`kpi-card__detail${trend ? ` kpi-card__detail--${trend}` : ''}`}>{detail}</span>
    </article>
  )
}
