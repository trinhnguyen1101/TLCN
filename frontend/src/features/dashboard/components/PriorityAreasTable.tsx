import { sectorLabel } from '../model/presentation'
import { useId, useMemo, useState } from 'react'
import type { PriorityArea, ProvinceCode } from '../types'
import { formatDecimal } from '../../../utils/formatters'
import { Field, Select } from '../../../components/ui/FormControls'
import { DataState } from '../../../components/ui/DataState'

interface PriorityAreasTableProps {
  areas: PriorityArea[]
  selectedProvinceCode: ProvinceCode | 'all'
  onProvinceSelect: (provinceCode: ProvinceCode) => void
}

const trendMeta: Record<NonNullable<PriorityArea['trend']>, { icon: string; label: string; className: string }> = {
  up: { icon: '↑', label: 'Tăng', className: 'text-danger bg-danger-soft' },
  'slight-up': { icon: '↑', label: 'Tăng nhẹ', className: 'text-danger bg-danger-soft' },
  steady: { icon: '→', label: 'Ổn định', className: 'text-secondary bg-surface-subtle' },
  down: { icon: '↓', label: 'Giảm', className: 'text-success bg-success-soft' },
}

const cellClasses = 'border-r border-b border-border px-3 py-[13px] text-left align-middle last:border-r-0'
const bodyCellClasses = [
  cellClasses,
  '[@media(max-width:760px)]:grid [@media(440px<width<=760px)]:grid-cols-[minmax(115px,.8fr)_minmax(0,1.2fr)] [@media(max-width:760px)]:items-center [@media(440px<width<=760px)]:gap-3 [@media(max-width:760px)]:border-r-0 [@media(max-width:760px)]:px-[11px] [@media(max-width:760px)]:py-2.5',
  '[@media(max-width:760px)]:before:text-[.64rem] [@media(max-width:760px)]:before:font-semibold [@media(max-width:760px)]:before:tracking-[.02em]',
  '[@media(max-width:760px)]:before:text-muted [@media(max-width:760px)]:before:uppercase [@media(max-width:760px)]:before:content-[attr(data-label)]',
  '[@media(max-width:440px)]:grid-cols-1 [@media(max-width:440px)]:gap-1.5',
].join(' ')
const headingCellClasses = `${cellClasses} sticky top-0 z-1 bg-surface-subtle text-[.68rem] leading-[1.35] font-semibold tracking-[.02em] text-muted uppercase`
const dataCellClasses = `${bodyCellClasses} text-[.75rem] text-secondary`

export function PriorityAreasTable({ areas, selectedProvinceCode, onProvinceSelect }: PriorityAreasTableProps) {
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('pm25-desc')
  const displayed = useMemo(() => areas.filter((area) => area.provinceName.toLocaleLowerCase('vi').includes(search.toLocaleLowerCase('vi'))).sort((a, b) => sort === 'name' ? a.provinceName.localeCompare(b.provinceName, 'vi') : sort === 'pm25-asc' ? (a.pm25Average ?? Infinity) - (b.pm25Average ?? Infinity) : (b.pm25Average ?? -Infinity) - (a.pm25Average ?? -Infinity)), [areas, search, sort])
  const titleId = `priority-areas-${useId().replaceAll(':', '')}`

  return (
    <section className="mt-0 overflow-hidden rounded-card border border-border bg-surface shadow-card" aria-labelledby={titleId}>
      <div className="flex items-start justify-between gap-[18px] border-b border-border bg-surface-subtle p-5 [@media(max-width:760px)]:flex-col [@media(max-width:760px)]:p-4">
        <div>
          <p>Khu vực ưu tiên · Các chỉ số môi trường</p>
          <h2 id={titleId} className="mt-1 mb-[7px] text-[clamp(1.05rem,2vw,1.25rem)] leading-[1.25] text-heading">Khu vực cần ưu tiên theo dõi</h2>
          <p className="m-0 max-w-[720px] text-[.78rem] leading-[1.45] text-muted">Số liệu môi trường theo từng tỉnh, thành phố trong khoảng thời gian đã chọn.</p>
        </div>
        <span className="flex-none rounded-full border border-border bg-surface px-2.5 py-[7px] text-[.68rem] text-secondary">Chưa có điểm ưu tiên</span>
      </div>

      <div className="grid grid-cols-2 gap-3 border-b border-border p-3">
        <Field>Tìm tỉnh, thành phố<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} className="h-10 w-full min-w-0 rounded-md border border-border-strong bg-surface px-3 text-xs text-ink focus-visible:outline-2 focus-visible:outline-accent" /></Field>
        <Field>Sắp xếp<Select aria-label="Sắp xếp" value={sort} onChange={(event) => setSort(event.target.value)}><option value="pm25-desc">PM2.5 cao đến thấp</option><option value="pm25-asc">PM2.5 thấp đến cao</option><option value="name">Tên tỉnh A–Z</option></Select></Field>
      </div>
      <DataState isEmpty={displayed.length === 0} emptyMessage="Không có khu vực phù hợp với bộ lọc hiện tại.">
        <div className="max-h-[350px] overflow-auto [@media(max-width:760px)]:max-h-[420px] [@media(max-width:760px)]:p-3" tabIndex={0} role="region" aria-label="Bảng khu vực ưu tiên">
          <table className="data-table w-full min-w-[1030px] border-collapse [@media(max-width:760px)]:min-w-0 [&_tbody_strong]:text-[.78rem] [&_tbody_strong]:font-semibold [&_tbody_strong]:text-heading">
            <thead className="[@media(max-width:760px)]:absolute [@media(max-width:760px)]:size-px [@media(max-width:760px)]:overflow-hidden [@media(max-width:760px)]:[clip:rect(0,0,0,0)] [@media(max-width:760px)]:whitespace-nowrap">
              <tr>
                <th scope="col" className={headingCellClasses}>Tỉnh, thành phố</th>
                <th scope="col" className={headingCellClasses}>PM2.5 trung bình</th>
                <th scope="col" className={headingCellClasses}>Thay đổi cùng kỳ (%)</th>
                <th scope="col" className={headingCellClasses}>Số ngày vượt ngưỡng</th>
                <th scope="col" className={headingCellClasses}>Tổng phát thải</th>
                <th scope="col" className={headingCellClasses}>Ngành phát thải chính</th>
                <th scope="col" className={headingCellClasses}>Xu hướng</th>
              </tr>
            </thead>
            <tbody className="[@media(max-width:760px)]:grid [@media(max-width:760px)]:gap-3 [&>tr:last-child>*]:border-b-0">
              {displayed.map((area) => {
                const trend = area.trend ? trendMeta[area.trend] : { icon: '—', label: 'Chưa có dữ liệu', className: 'text-secondary bg-surface-subtle' }
                const isSelected = selectedProvinceCode === area.provinceCode
                const yoyClass = (area.yearOverYearPercent ?? 0) >= 10
                  ? 'text-danger!'
                  : (area.yearOverYearPercent ?? 0) < 0
                    ? 'text-success!'
                    : ''

                return (
                  <tr key={area.provinceCode} data-selected={isSelected} className="[@media(max-width:760px)]:grid [@media(max-width:760px)]:rounded-[10px] [@media(max-width:760px)]:border [@media(max-width:760px)]:border-border [@media(max-width:760px)]:shadow-card">
                    <th scope="row" data-label="Tỉnh, thành phố" className={`${bodyCellClasses} w-[178px] [@media(max-width:760px)]:w-auto`}>
                      <button
                        type="button"
                        className="grid w-full cursor-pointer gap-1 border-0 bg-transparent p-0 text-left font-semibold text-accent no-underline hover:text-accent-hover hover:underline hover:underline-offset-[3px] [@media(max-width:760px)]:min-w-0"
                        aria-pressed={isSelected}
                        onClick={() => onProvinceSelect(area.provinceCode)}
                      >
                        {area.provinceName}
                        <span className="text-[.62rem] font-normal text-muted">Chọn để lọc dữ liệu →</span>
                      </button>
                    </th>
                    <td data-label="PM2.5 trung bình" className={dataCellClasses}>
                      <div className="grid min-w-[120px] gap-[7px] [@media(max-width:760px)]:min-w-0">
                        <strong>{formatDecimal(area.pm25Average)}{area.pm25Average === null ? '' : ' µg/m³'}</strong>
                        <span className="block h-[7px] overflow-hidden rounded-[99px] bg-surface-subtle" aria-hidden="true">
                          <i className="block h-full rounded-[inherit] bg-accent" style={{ width: `${Math.min(100, ((area.pm25Average ?? 0) / 50) * 100)}%` }} />
                        </span>
                      </div>
                    </td>
                    <td data-label="Thay đổi cùng kỳ (%)" className={dataCellClasses}>
                      <strong className={yoyClass}>{area.yearOverYearPercent === null ? 'Chưa có dữ liệu' : `${area.yearOverYearPercent > 0 ? '+' : ''}${formatDecimal(area.yearOverYearPercent)}%`}</strong>
                    </td>
                    <td data-label="Số ngày vượt ngưỡng" className={dataCellClasses}>
                      <strong className={area.exceedanceDays !== null && area.exceedanceDays >= 30 ? 'text-danger!' : ''}>{area.exceedanceDays === null ? 'Chưa có dữ liệu' : `${area.exceedanceDays} ngày`}</strong>
                    </td>
                    <td data-label="Tổng phát thải" className={dataCellClasses}>
                      <strong>{area.totalEmissions === null ? 'Chưa có dữ liệu' : `${Math.round(area.totalEmissions).toLocaleString('vi-VN')} tấn`}</strong>
                    </td>
                    <td data-label="Ngành phát thải chính" className={dataCellClasses}>{area.mainEmissionSector ? sectorLabel(area.mainEmissionSector) : 'Chưa có dữ liệu'}</td>
                    <td data-label="Xu hướng" className={dataCellClasses}>
                      <span className={`inline-flex items-center gap-[5px] rounded-full border border-border px-2 py-[5px] whitespace-nowrap ${trend.className}`} aria-label={`Xu hướng ${trend.label.toLowerCase()}`}>
                        <b className="text-[.9rem] leading-[.7]" aria-hidden="true">{trend.icon}</b> {trend.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </DataState>
    </section>
  )
}
