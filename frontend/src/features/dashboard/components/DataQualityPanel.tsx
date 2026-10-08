import type { DashboardData, DashboardFiltersValue } from '../types'
import { isNumber, matchesPeriod, METRIC_META } from '../model/dashboardSelectors'
import { aggregationLabel, sourceLabel } from '../model/presentation'
import { formatDateTime } from '../../../utils/dates'

export function DataQualityPanel({ data, filters }: { data: DashboardData | null; filters: DashboardFiltersValue }) {
  const rows = (data?.dashboardTrendRecords ?? []).filter((row) => matchesPeriod(row, filters))
  const valid = rows.filter((row) => isNumber(row[filters.pollutant])).length
  const provinces = new Set(rows.filter((row) => isNumber(row[filters.pollutant])).map((row) => row.provinceCode)).size
  return <section className="rounded-card border border-border bg-surface p-5">
    <h2 className="text-sm font-semibold text-heading">Độ đầy đủ của dữ liệu · {METRIC_META[filters.pollutant].label}</h2>
    <dl className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">{[
      ['Số bản ghi', String(rows.length)], ['Bản ghi có giá trị hợp lệ', String(valid)], ['Bản ghi thiếu hoặc sai giá trị', String(rows.length - valid)], ['Tỉnh có dữ liệu', String(provinces)],
    ].map(([label, value]) => <div key={label}><dt className="text-xs text-muted">{label}</dt><dd className="mt-2 text-2xl font-semibold text-heading tabular-nums">{data ? value : '—'}</dd></div>)}</dl>
    <p className="mt-4 text-xs leading-relaxed text-muted">{rows.length ? `${(valid / rows.length * 100).toFixed(1)}% bản ghi nhận được có giá trị số hợp lệ. ` : ''}Thống kê chỉ dựa trên dữ liệu đã nhận, chưa bao gồm các bản ghi mà nguồn chưa gửi.</p>
    {data?.metadata && <dl className="mt-4 grid gap-2 border-t border-border pt-4 text-xs text-muted"><div><dt className="inline font-medium">Nguồn: </dt><dd className="inline">{sourceLabel(data.metadata.source)}</dd></div><div><dt className="inline font-medium">Cách tổng hợp dữ liệu: </dt><dd className="inline">{aggregationLabel(data.metadata.temporalAggregation)} · {data.metadata.timezone}</dd></div><div><dt className="inline font-medium">Thời gian có dữ liệu: </dt><dd className="inline">{formatDateTime(data.metadata.start)} → {formatDateTime(data.metadata.end)}</dd></div></dl>}
  </section>
}
