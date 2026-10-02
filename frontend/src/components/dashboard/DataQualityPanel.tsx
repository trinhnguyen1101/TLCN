import type { DashboardData, DashboardFiltersValue } from '../../types/dashboard'
import { isNumber, matchesPeriod, METRIC_META } from '../../services/dashboardSelectors'

export function DataQualityPanel({ data, filters }: { data: DashboardData | null; filters: DashboardFiltersValue }) {
  const rows = (data?.dashboardTrendRecords ?? []).filter((row) => matchesPeriod(row, filters))
  const valid = rows.filter((row) => isNumber(row[filters.pollutant])).length
  const provinces = new Set(rows.filter((row) => isNumber(row[filters.pollutant])).map((row) => row.provinceCode)).size
  return <section className="rounded-card border border-border bg-surface p-5">
    <h2 className="text-sm font-semibold text-heading">Kiểm tra dữ liệu · {METRIC_META[filters.pollutant].label}</h2>
    <dl className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">{[
      ['Bản ghi trong kỳ', String(rows.length)], ['Giá trị số hợp lệ', String(valid)], ['Giá trị thiếu / không hợp lệ', String(rows.length - valid)], ['Tỉnh có giá trị', String(provinces)],
    ].map(([label, value]) => <div key={label}><dt className="text-xs text-muted">{label}</dt><dd className="mt-2 text-2xl font-semibold text-heading tabular-nums">{data ? value : '—'}</dd></div>)}</dl>
    <p className="mt-4 text-xs leading-relaxed text-muted">{rows.length ? `${(valid / rows.length * 100).toFixed(1)}% bản ghi nhận được có giá trị số hợp lệ. ` : ''}Phép đếm trên dữ liệu đã nhận; chưa đo các bản ghi không được gửi từ nguồn.</p>
    {data?.metadata && <dl className="mt-4 grid gap-2 border-t border-border pt-4 text-xs text-muted"><div><dt className="inline font-medium">Nguồn: </dt><dd className="inline">{data.metadata.source}</dd></div><div><dt className="inline font-medium">Độ phân giải thời gian: </dt><dd className="inline">{data.metadata.temporalAggregation} · {data.metadata.timezone}</dd></div><div><dt className="inline font-medium">Khoảng dữ liệu nguồn: </dt><dd className="inline">{data.metadata.start} → {data.metadata.end}</dd></div></dl>}
  </section>
}
