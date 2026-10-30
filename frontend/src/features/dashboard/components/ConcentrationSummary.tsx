import type { DashboardTrendRecord, Pollutant } from '../types'
import { isNumber } from '../model/dashboardSelectors'
import { formatDecimal } from '../../../utils/formatters'

export function ConcentrationSummary({ label, unit, value, pollutant, records, scope, period, loading }: {
  label: string; unit: string; value: number | null; pollutant: Pollutant; records: DashboardTrendRecord[]; scope: string; period: string; loading: boolean
}) {
  const values = records.map(row => row[pollutant]).filter(isNumber)
  const minimum = values.length ? values.reduce((a,b) => Math.min(a,b), Infinity) : null
  const maximum = values.length ? values.reduce((a,b) => Math.max(a,b), -Infinity) : null
  return <section className="overflow-hidden rounded-card border border-accent-border border-t-4 border-t-accent bg-surface p-5 shadow-card" aria-busy={loading}>
    <p className="text-xs font-semibold uppercase tracking-wider text-accent">{scope}</p>
    <h2 className="mt-2 text-sm font-medium text-secondary">{label} · trung bình phạm vi chọn</h2>
    <p className="mt-3 text-4xl font-semibold tracking-tight text-heading tabular-nums">{loading ? '…' : formatDecimal(value, unit, false)} <span className="text-base font-normal text-muted">{unit}</span></p>
    <p className="mt-3 text-xs leading-relaxed text-muted">{period}</p>
    <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 text-xs"><div><dt className="text-muted">Thấp nhất</dt><dd className="mt-1 font-semibold text-heading">{formatDecimal(minimum, unit)}</dd></div><div><dt className="text-muted">Cao nhất</dt><dd className="mt-1 font-semibold text-heading">{formatDecimal(maximum, unit)}</dd></div></dl>
    <p className="mt-3 text-[.7rem] leading-relaxed text-muted">Ước tính mô hình · AQI —</p>
  </section>
}
