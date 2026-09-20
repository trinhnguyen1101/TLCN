import { useId } from 'react'
import { DataState } from '../../components/dashboard/DataState'
import { ExportActions } from '../../components/dashboard/ExportActions'
import './HorizontalBarChart.css'

export interface HorizontalBarPoint {
  id: string
  label: string
  value: number
}

interface HorizontalBarChartProps {
  eyebrow: string
  title: string
  description: string
  points: HorizontalBarPoint[]
  unit: string
  fileName: string
  selectedId?: string
  onSelect?: (point: HorizontalBarPoint) => void
}

const WIDTH = 560
const LABEL_WIDTH = 165
const VALUE_WIDTH = 80
const BAR_HEIGHT = 34
const ROW_GAP = 18
const TOP = 22

const shortenLabel = (label: string) => label.length > 22 ? `${label.slice(0, 21)}…` : label

export function HorizontalBarChart({ eyebrow, title, description, points, unit, fileName, selectedId, onSelect }: HorizontalBarChartProps) {
  const chartId = `bars-${useId().replaceAll(':', '')}`
  const maxValue = Math.max(...points.map((point) => point.value), 1)
  const height = Math.max(170, TOP * 2 + points.length * (BAR_HEIGHT + ROW_GAP) - ROW_GAP)
  const barAreaWidth = WIDTH - LABEL_WIDTH - VALUE_WIDTH

  return (
    <section className="ranking-card" aria-labelledby={`${chartId}-title`}>
      <div className="ranking-card__header">
        <div>
          <div className="trend-title-row">
            <p className="eyebrow">{eyebrow}</p>
            <span className="info-tooltip" tabIndex={0} aria-label={description}>i<span role="tooltip">{description}</span></span>
          </div>
          <h2 id={`${chartId}-title`}>{title}</h2>
        </div>
        <ExportActions
          chartId={chartId}
          fileName={fileName}
          csvRows={points.map((point, index) => ({ Hang: index + 1, Ten: point.label, Gia_tri: point.value, Don_vi: unit }))}
        />
      </div>

      <DataState isEmpty={points.length === 0} emptyMessage="Không có dữ liệu xếp hạng theo bộ lọc hiện tại.">
        <div className="ranking-card__scroll">
          <svg id={chartId} className="horizontal-bar-chart" viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={`${title}. ${points.length} mục dữ liệu.`}>
            <rect width={WIDTH} height={height} fill="#fffaf0" />
            {points.map((point, index) => {
              const y = TOP + index * (BAR_HEIGHT + ROW_GAP)
              const width = Math.max(4, (point.value / maxValue) * barAreaWidth)
              const isSelected = selectedId === point.id
              return (
                <g
                  key={point.id}
                  className={`horizontal-bar-chart__row${onSelect ? ' is-interactive' : ''}${isSelected ? ' is-selected' : ''}`}
                  tabIndex={onSelect ? 0 : undefined}
                  role={onSelect ? 'button' : undefined}
                  aria-label={`${point.label}: ${point.value.toLocaleString('vi-VN')} ${unit}${onSelect ? '. Nhấn để lọc dashboard.' : ''}`}
                  onClick={() => onSelect?.(point)}
                  onKeyDown={(event) => {
                    if (onSelect && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault()
                      onSelect(point)
                    }
                  }}
                >
                  <title>{point.label}: {point.value.toLocaleString('vi-VN')} {unit}</title>
                  <text x={LABEL_WIDTH - 14} y={y + 22} textAnchor="end">{index + 1}. {shortenLabel(point.label)}</text>
                  <rect className="horizontal-bar-chart__track" x={LABEL_WIDTH} y={y} width={barAreaWidth} height={BAR_HEIGHT} />
                  <rect className="horizontal-bar-chart__bar" x={LABEL_WIDTH} y={y} width={width} height={BAR_HEIGHT} />
                  <text className="horizontal-bar-chart__value" x={LABEL_WIDTH + barAreaWidth + 12} y={y + 22}>{point.value.toLocaleString('vi-VN')}</text>
                </g>
              )
            })}
          </svg>
        </div>
      </DataState>
    </section>
  )
}
