import type { DashboardData, DashboardFiltersValue } from '../types'
import { dataQuality } from '../model/dataQuality'
import { isNumber, METRIC_META } from '../model/dashboardSelectors'
import { formatDate } from '../../../utils/dates'
import { aggregationLabel, sourceLabel } from '../../../utils/labels'

export function DataQualityPanel({ data, filters }: { data: DashboardData | null; filters: DashboardFiltersValue }) {
  const { rows, valid, expected, missing, hourly, sourceSamples } = dataQuality(data, filters)
  const provinces = new Set(rows.filter((row) => isNumber(row[filters.pollutant])).map((row) => row.provinceCode)).size
  return <section className="rounded-card border border-border bg-surface p-5">
    <h2 className="text-sm font-semibold text-heading">Kiểm tra dữ liệu · {METRIC_META[filters.pollutant].label}</h2>
    <dl className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">{[
      [sourceSamples ? 'Số mẫu nguồn kỳ vọng' : 'Số mẫu kỳ vọng', String(expected)], ['Slot hợp lệ', String(valid)], ['Giá trị thiếu / không hợp lệ', String(missing)], ['Tỉnh có giá trị', String(provinces)],
    ].map(([label, value]) => <div key={label}><dt className="text-xs text-muted">{label}</dt><dd className="mt-2 text-2xl font-semibold text-heading tabular-nums">{data ? value : '—'}</dd></div>)}</dl>
    <p className="mt-4 text-xs leading-relaxed text-muted">{expected ? `${(valid / expected * 100).toFixed(1)}% độ phủ · ${(missing / expected * 100).toFixed(1)}% thiếu. ` : ''}{sourceSamples ? 'Đếm mẫu nguồn hợp lệ trước khi tính trung bình; ngày/tháng cần ít nhất 75% mẫu. Mẫu thiếu không được bù.' : hourly ? 'Bao gồm cả mốc giờ vắng hoàn toàn trong phạm vi đã chọn.' : 'Đếm theo bản ghi tổng hợp; trung bình ngày/tháng cần ít nhất 75% mẫu hợp lệ.'}</p>
    <details className="mt-3 border-t border-border pt-3 text-xs text-muted"><summary className="cursor-pointer">Nguồn, chuyển đổi & phiên bản ⓘ</summary>
    {data?.metadata?.temporalOrigin && <p className="mt-3 rounded-lg bg-accent-soft p-3 text-xs text-accent">{data.metadata.temporalOrigin === 'interpolated' ? 'Nội suy thời gian từ CAMS EAC4 3 giờ; các giờ trung gian không phải quan sát gốc.' : `Nguồn gốc thời gian: ${data.metadata.temporalOrigin}`} AQI không được suy từ nồng độ này.</p>}
    {data?.metadata?.generation && <p className="mt-3 break-all font-mono text-[.7rem] text-muted">Generation: {data.metadata.generation}</p>}
    {data?.metadata?.publishedReleaseId && <p className="mt-4 text-xs text-muted">{data.metadata.note}</p>}
    {data?.metadata && <dl className="mt-4 grid gap-2 border-t border-border pt-4 text-xs text-muted"><div><dt className="inline font-medium">Nguồn: </dt><dd className="inline">{sourceLabel(data.metadata.source)}</dd></div><div><dt className="inline font-medium">Độ phân giải thời gian: </dt><dd className="inline">{aggregationLabel(data.metadata.temporalAggregation)} · {data.metadata.timezone}</dd></div><div><dt className="inline font-medium">Khoảng dữ liệu nguồn: </dt><dd className="inline">{formatDate(data.metadata.start)} → {formatDate(data.metadata.end)}</dd></div></dl>}
      {data?.metadata?.samplingNote && <p className="mt-3">{data.metadata.samplingNote}</p>}
      {data?.metadata && <div className="mt-3 overflow-auto"><table className="data-table w-full text-left text-xs"><thead><tr><th>Chỉ số</th><th>Đơn vị</th><th>Tầng</th><th>Chuyển đổi</th></tr></thead><tbody>{Object.entries(data.metadata.metrics).map(([key,value])=>value&&<tr key={key}><td>{value.displayName??key}</td><td>{value.sourceUnit} → {value.unit}</td><td>{value.sourceLevelType} {value.sourceLevel}</td><td>{value.conversionMethod}</td></tr>)}</tbody></table></div>}
    </details>
  </section>
}
