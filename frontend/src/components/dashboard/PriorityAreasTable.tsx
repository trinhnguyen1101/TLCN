import { useId } from 'react'
import type { PriorityArea, ProvinceCode } from '../../types/dashboard'
import { formatDecimal } from '../../utils/formatters'
import { DataState } from './DataState'
import './PriorityAreasTable.css'

interface PriorityAreasTableProps {
  areas: PriorityArea[]
  selectedProvinceCode: ProvinceCode | 'all'
  onProvinceSelect: (provinceCode: ProvinceCode) => void
}

const trendMeta: Record<NonNullable<PriorityArea['trend']>, { icon: string; label: string }> = {
  up: { icon: '↑', label: 'Tăng' },
  'slight-up': { icon: '↑', label: 'Tăng nhẹ' },
  steady: { icon: '→', label: 'Ổn định' },
  down: { icon: '↓', label: 'Giảm' },
}

export function PriorityAreasTable({ areas, selectedProvinceCode, onProvinceSelect }: PriorityAreasTableProps) {
  const titleId = `priority-areas-${useId().replaceAll(':', '')}`

  return (
    <section className="priority-areas" aria-labelledby={titleId}>
      <div className="priority-areas__header">
        <div>
          <p className="eyebrow">Priority Areas · Tổng hợp đa chỉ số</p>
          <h2 id={titleId}>KHU VỰC CẦN ƯU TIÊN THEO DÕI</h2>
          <p>Các khu vực có nhiều chỉ số môi trường cần chú ý trong kỳ báo cáo.</p>
        </div>
        <span className="priority-areas__note">Không chấm điểm ưu tiên</span>
      </div>

      <DataState isEmpty={areas.length === 0} emptyMessage="Không có khu vực phù hợp với bộ lọc hiện tại.">
        <div className="priority-areas__scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Tỉnh / Thành</th>
                <th scope="col">PM2.5 trung bình</th>
                <th scope="col">Thay đổi YoY (%)</th>
                <th scope="col">Số ngày vượt ngưỡng</th>
                <th scope="col">Tổng phát thải</th>
                <th scope="col">Ngành phát thải chính</th>
                <th scope="col">Xu hướng</th>
              </tr>
            </thead>
            <tbody>
              {areas.map((area) => {
                const trend = area.trend ? trendMeta[area.trend] : { icon: '—', label: 'Chưa có dữ liệu' }
                const isSelected = selectedProvinceCode === area.provinceCode
                const yoyClass = (area.yearOverYearPercent ?? 0) >= 10
                  ? 'priority-value--alert'
                  : (area.yearOverYearPercent ?? 0) < 0
                    ? 'priority-value--positive'
                    : ''

                return (
                  <tr key={area.provinceCode} className={isSelected ? 'is-selected' : undefined}>
                    <th scope="row" data-label="Tỉnh / Thành">
                      <button
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => onProvinceSelect(area.provinceCode)}
                      >
                        {area.provinceName}
                        <span>Chọn để lọc dashboard →</span>
                      </button>
                    </th>
                    <td data-label="PM2.5 trung bình">
                      <div className="priority-pm25">
                        <strong>{formatDecimal(area.pm25Average)}{area.pm25Average === null ? '' : ' µg/m³'}</strong>
                        <span className="priority-pm25__track" aria-hidden="true">
                          <i style={{ width: `${Math.min(100, ((area.pm25Average ?? 0) / 50) * 100)}%` }} />
                        </span>
                      </div>
                    </td>
                    <td data-label="Thay đổi YoY (%)">
                      <strong className={yoyClass}>{area.yearOverYearPercent === null ? 'Chưa có dữ liệu' : `${area.yearOverYearPercent > 0 ? '+' : ''}${formatDecimal(area.yearOverYearPercent)}%`}</strong>
                    </td>
                    <td data-label="Số ngày vượt ngưỡng">
                      <strong className={area.exceedanceDays !== null && area.exceedanceDays >= 30 ? 'priority-value--alert' : ''}>{area.exceedanceDays === null ? 'Chưa có dữ liệu' : `${area.exceedanceDays} ngày`}</strong>
                    </td>
                    <td data-label="Tổng phát thải">
                      <strong>{area.totalEmissions === null ? 'Chưa có dữ liệu' : `${Math.round(area.totalEmissions).toLocaleString('vi-VN')} tấn`}</strong>
                    </td>
                    <td data-label="Ngành phát thải chính">{area.mainEmissionSector ?? 'Chưa có dữ liệu'}</td>
                    <td data-label="Xu hướng">
                      <span className={`priority-trend priority-trend--${area.trend}`} aria-label={`Xu hướng ${trend.label.toLowerCase()}`}>
                        <b aria-hidden="true">{trend.icon}</b> {trend.label}
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
