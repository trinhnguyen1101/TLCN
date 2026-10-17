import { useMemo, useState } from 'react'
import type { DashboardTrendRecord, Pollutant, ProvinceSnapshot } from '../types'
import { Button } from '../../../components/ui/Button'
import { DataState } from '../../../components/ui/DataState'
import { DashboardSkeleton } from '../../../components/ui/DashboardSkeleton'
import { ExportActions } from '../../../components/ui/ExportActions'
import { formatDateTime } from '../../../utils/dates'

interface ObservationTableProps {
  records: DashboardTrendRecord[]
  provinces: ProvinceSnapshot[]
  provinceCode: string
  pollutant: Pollutant
  metricLabel: string
  unit: string
  dataReady: boolean
  loading: boolean
}

const PAGE_SIZE = 50

export function ObservationTable({ records, provinces, provinceCode, pollutant, metricLabel, unit, dataReady, loading }: ObservationTableProps) {
  const [selection, setPage] = useState(0)
  const names = useMemo(() => new Map(provinces.map((province) => [province.provinceCode, province.provinceName])), [provinces])
  const rows = useMemo(() => records.filter((record) => provinceCode === 'all' || record.provinceCode === provinceCode), [records, provinceCode])
  const page = Math.min(selection, Math.max(0, Math.ceil(rows.length / PAGE_SIZE) - 1))
  const csvRows = useMemo(() => dataReady ? rows.map((row) => ({ Thoi_gian_UTC: row.date, Ma_vung: row.provinceCode,
    Ten_vung: names.get(row.provinceCode) ?? row.provinceCode, [metricLabel]: row[pollutant] ?? null, Don_vi: unit })) : [], [dataReady, rows, names, metricLabel, pollutant, unit])
  return (
    <section className="observation-panel mx-auto mt-6 w-full min-w-0 max-w-[960px] overflow-hidden rounded-card border border-border bg-surface shadow-card" aria-label="Bảng dữ liệu theo thời gian">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4 max-sm:px-4">
        <div className="min-w-0"><h2 className="font-semibold text-heading">Chi tiết dữ liệu · {metricLabel}</h2><p className="mt-1.5 max-w-[600px] text-xs leading-relaxed text-muted">Mỗi dòng là số liệu của một tỉnh, thành phố tại một thời điểm. Xuất CSV để tải toàn bộ dữ liệu đang xem.</p></div>
        <ExportActions fileName={`quan-sat-${pollutant}-${provinceCode}`} csvRows={csvRows} />
      </div>
      {!dataReady ? <DashboardSkeleton variant="table" loading={loading} /> : <DataState compact isEmpty={!rows.length} emptyMessage="Không có dữ liệu trong khoảng thời gian đã chọn.">
        <p className="border-b border-border bg-surface-subtle px-4 py-2 text-xs text-muted sm:hidden">Vuốt ngang để xem đầy đủ các cột.</p>
        <div className="max-h-[420px] overflow-auto" tabIndex={0} role="region" aria-label="Chi tiết dữ liệu theo tỉnh, thành phố">
          <table className="observation-table data-table w-full min-w-[520px] table-fixed border-separate border-spacing-0 text-left text-sm">
            <colgroup><col className="w-[32%]" /><col className="w-[40%]" /><col className="w-[28%]" /></colgroup>
            <thead className="sticky top-0 z-1 bg-surface-subtle text-xs text-secondary"><tr><th scope="col">Thời gian (UTC)</th><th scope="col">Tỉnh, thành phố</th><th scope="col" className="text-right">{metricLabel}{unit && <span className="mt-1 block font-normal text-muted">{unit}</span>}</th></tr></thead>
            <tbody>{rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((row) => <tr key={`${row.provinceCode}-${row.date}`}><td className="whitespace-nowrap text-secondary tabular-nums"><time dateTime={row.date}>{formatDateTime(row.date)}</time></td><th scope="row" className="font-medium text-heading">{names.get(row.provinceCode) ?? row.provinceCode}</th><td className={`text-right tabular-nums ${row[pollutant] == null ? 'text-xs text-muted' : 'font-semibold text-heading'}`}>{row[pollutant]?.toLocaleString('vi-VN', { maximumFractionDigits: 3 }) ?? 'Chưa có dữ liệu'}</td></tr>)}</tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3 text-xs text-muted max-sm:px-4"><span>Đang xem {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, rows.length)} trong {rows.length.toLocaleString('vi-VN')} dòng</span><div className="flex gap-2"><Button disabled={page === 0} onClick={() => setPage(page - 1)}>Trang trước</Button><Button disabled={(page + 1) * PAGE_SIZE >= rows.length} onClick={() => setPage(page + 1)}>Trang sau</Button></div></div>
      </DataState>}
    </section>
  )
}
