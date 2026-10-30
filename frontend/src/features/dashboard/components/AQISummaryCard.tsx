import { aqiLevel } from '../../geography/mapColorScale'
import { formatDate } from '../../../utils/dates'

interface AQISummaryCardProps {
  aqi: number | null
  scopeLabel: string
  period: string
  snapshotDate?: string | null
  calendarTimezone?: string
  loading?: boolean
}

export function AQISummaryCard({ aqi, scopeLabel, period, snapshotDate, calendarTimezone = 'UTC', loading }: AQISummaryCardProps) {
  const level = aqiLevel(aqi)
  return <section className="overflow-hidden rounded-card border border-border border-t-4 bg-surface p-5 shadow-card" style={{ borderTopColor: level?.color ?? 'var(--color-accent)' }} aria-label="Tóm tắt AQI" aria-busy={loading}>
    <p className="text-xs font-medium text-muted">{period}</p>
    <h2 className="mt-2 text-lg font-semibold text-heading">{scopeLabel}</h2>
    <div className="my-4 flex flex-wrap items-center gap-3">
      <strong className={aqi === null ? 'text-xl text-muted' : 'text-5xl font-semibold tabular-nums'} style={{ color: level?.textColor }}>{loading ? 'Đang tải…' : aqi === null ? 'Chưa có dữ liệu AQI' : Math.round(aqi)}</strong>
      {level && <span className="rounded-full border px-3 py-1 text-xs font-semibold" style={{ color: level.textColor, borderColor: `${level.color}60`, backgroundColor: `${level.color}15` }}>{level.label}</span>}
    </div>
    <p className="text-xs leading-relaxed text-muted">{aqi === null ? 'Nguồn hiện tại không cung cấp AQI hợp lệ cho lựa chọn này. Xem nồng độ các chất bên dưới.' : 'AQI tại tỉnh và mốc thời gian đang chọn.'}</p>
    <p className="mt-2 text-xs text-muted">{snapshotDate ? `Kỳ dữ liệu: ${formatDate(snapshotDate)} (${calendarTimezone})` : 'Thời gian và phạm vi áp dụng hiển thị ở trên'}</p>
  </section>
}
