import type { DashboardData, DashboardFiltersValue } from '../types'
import { DataState } from '../../../components/ui/DataState'
import { DashboardSkeleton } from '../../../components/ui/DashboardSkeleton'
import { matchesEmissionPeriod } from '../model/dashboardSelectors'
import { sectorLabel } from '../../../utils/labels'

export function EmissionTable({ data, filters, loading }: { data: DashboardData | null; filters: DashboardFiltersValue; loading: boolean }) {
  const rows = (data?.emissionRecords ?? []).filter((row) => matchesEmissionPeriod(row, filters))
  return <section className="min-w-0 overflow-hidden rounded-card border border-border bg-surface">
    <h2 className="p-4 text-sm font-semibold text-heading">Chi tiết phát thải theo ngành</h2>
    {(filters.startDate || filters.endDate) && <p className="px-4 pb-3 text-xs text-muted">Số liệu phát thải được tổng hợp theo tháng, bao gồm toàn bộ các tháng giao với khoảng ngày đã chọn.</p>}
    {!data ? <DashboardSkeleton variant="table" loading={loading} /> : <DataState isEmpty={!rows.length} emptyMessage="Không có số liệu phát thải trong kỳ đang chọn."><div className="max-h-[320px] overflow-auto" tabIndex={0} role="region" aria-label="Bảng phát thải"><table className="w-full border-separate border-spacing-0 text-left text-xs text-secondary"><thead className="sticky top-0 bg-surface-subtle"><tr>{['Tỉnh / thành', 'Kỳ', 'Ngành', 'Phát thải (tấn)'].map((label) => <th scope="col" key={label} className="whitespace-nowrap border-y border-border p-3">{label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={`${row.provinceCode}-${row.year}-${row.month}-${sectorLabel(row.sector)}`} className="hover:bg-surface-subtle"><td className="border-b border-border p-3">{row.provinceName}</td><td className="border-b border-border p-3">{row.month}/{row.year}</td><td className="border-b border-border p-3">{sectorLabel(row.sector)}</td><td className="border-b border-border p-3 tabular-nums">{row.emissionTonnes.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}</td></tr>)}</tbody></table></div></DataState>}
  </section>
}
