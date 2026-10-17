import { sectorLabel } from '../model/presentation'
import type { DashboardData, DashboardFiltersValue } from '../types'
import { DataState } from '../../../components/ui/DataState'
import { DashboardSkeleton } from '../../../components/ui/DashboardSkeleton'

export function EmissionTable({ data, filters, loading }: { data: DashboardData | null; filters: DashboardFiltersValue; loading: boolean }) {
  const rows = (data?.emissionRecords ?? []).filter((row) => {
    const month = `${row.year}-${String(row.month).padStart(2, '0')}`
    return (filters.provinceCode === 'all' || row.provinceCode === filters.provinceCode)
      && (filters.year === 'all' || row.year === filters.year)
      && (filters.month === 'all' || row.month === filters.month)
      && (filters.sector === 'all' || row.sector === filters.sector)
      && (!filters.startDate || month >= filters.startDate.slice(0, 7))
      && (!filters.endDate || month <= filters.endDate.slice(0, 7))
  })
  return <section className="min-w-0 overflow-hidden rounded-card border border-border bg-surface">
    <h2 className="p-4 text-sm font-semibold text-heading">Chi tiết phát thải theo ngành</h2>
    {!data ? <DashboardSkeleton variant="table" loading={loading} /> : <DataState isEmpty={!rows.length} emptyMessage="Không có số liệu phát thải trong khoảng thời gian đã chọn."><div className="max-h-[320px] overflow-auto" tabIndex={0} role="region" aria-label="Bảng phát thải"><table className="data-table w-full border-separate border-spacing-0 text-left text-xs text-secondary"><thead className="sticky top-0 bg-surface-subtle"><tr>{['Tỉnh, thành phố', 'Tháng', 'Ngành', 'Phát thải (tấn)'].map((label) => <th scope="col" key={label} className="whitespace-nowrap border-y border-border p-3">{label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={`${row.provinceCode}-${row.year}-${row.month}-${row.sector}`} className="hover:bg-surface-subtle"><td className="border-b border-border p-3">{row.provinceName}</td><td className="border-b border-border p-3">{String(row.month).padStart(2, '0')}/{row.year}</td><td className="border-b border-border p-3">{sectorLabel(row.sector)}</td><td className="border-b border-border p-3 tabular-nums">{row.emissionTonnes.toLocaleString('vi-VN', { maximumFractionDigits: 1 })}</td></tr>)}</tbody></table></div></DataState>}
  </section>
}
