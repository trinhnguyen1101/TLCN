import { useId } from 'react'
import { DashboardSkeleton } from '../../components/dashboard/DashboardSkeleton'
import { DataState } from '../../components/dashboard/DataState'
import { ExportActions } from '../../components/dashboard/ExportActions'

export interface HorizontalBarPoint {
  id: string
  label: string
  value: number
}

interface HorizontalBarChartProps {
  compact?: boolean
  dataReady?: boolean
  loading?: boolean
  eyebrow: string
  title: string
  description: string
  points: HorizontalBarPoint[]
  unit: string
  fileName: string
  selectedId?: string
  onSelect?: (point: HorizontalBarPoint) => void
}

const labelClasses = 'fill-muted font-sans text-[12px] font-medium'

const WIDTH = 560
const LABEL_WIDTH = 165
const VALUE_WIDTH = 80
const BAR_HEIGHT = 34
const ROW_GAP = 18
const TOP = 22

const shortenLabel = (label: string) => label.length > 22 ? `${label.slice(0, 21)}…` : label

export function HorizontalBarChart({ compact = false, dataReady = true, loading = false, eyebrow, title, description, points, unit, fileName, selectedId, onSelect }: HorizontalBarChartProps) {
  const chartId = `bars-${useId().replaceAll(':', '')}`
  const maxValue = Math.max(...points.map((point) => Math.abs(point.value)), 1)
  const hasNegative = points.some((point) => point.value < 0)
  const height = Math.max(170, TOP * 2 + points.length * (BAR_HEIGHT + ROW_GAP) - ROW_GAP)
  const barAreaWidth = WIDTH - LABEL_WIDTH - VALUE_WIDTH

  return (
    <section className="overflow-hidden rounded-card border border-border bg-surface shadow-card" aria-labelledby={`${chartId}-title`}>
      <div className="flex items-start justify-between gap-4 px-4 pt-4 pb-1 [@media(max-width:620px)]:flex-col">
        <div>
          <p className="text-xs text-muted">{eyebrow}</p>
          <h2 id={`${chartId}-title`} className="mt-1 text-[1.02rem] font-semibold text-heading">{title}</h2>
        </div>
        <ExportActions
          chartId={chartId}
          fileName={fileName}
          csvRows={points.map((point, index) => ({ Hang: index + 1, Ten: point.label, Gia_tri: point.value, Don_vi: unit }))}
        />
      </div>

      {!dataReady ? <DashboardSkeleton variant="chart" loading={loading} /> : <DataState isEmpty={points.length === 0} emptyMessage="Không có dữ liệu xếp hạng theo bộ lọc hiện tại.">
        <div className="overflow-x-auto px-3 pt-1 pb-3">
          <svg id={chartId} className={`block h-auto w-full min-w-0 ${compact ? 'max-h-[175px]' : 'max-h-[300px]'}`} viewBox={`0 0 ${WIDTH} ${height}`} role="img" aria-label={`${title}. ${points.length} mục dữ liệu.`}><desc>{description}</desc>
            <rect className="fill-surface" width={WIDTH} height={height} />
            {points.map((point, index) => {
              const y = TOP + index * (BAR_HEIGHT + ROW_GAP)
              const width = Math.max(0, (Math.abs(point.value) / maxValue) * barAreaWidth / (hasNegative ? 2 : 1))
              const baseline = LABEL_WIDTH + (hasNegative ? barAreaWidth / 2 : 0)
              const isSelected = selectedId === point.id
              return (
                <g
                  key={point.id}
                  className={onSelect ? 'group cursor-pointer focus:outline-none' : undefined}
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
                  <text className={labelClasses} x={LABEL_WIDTH - 14} y={y + 22} textAnchor="end">{index + 1}. {shortenLabel(point.label)}</text>
                  <rect className={`fill-surface-subtle ${isSelected ? 'stroke-accent stroke-2' : 'stroke-border stroke-1'}`} x={LABEL_WIDTH} y={y} width={barAreaWidth} height={BAR_HEIGHT} />
                  <rect className={isSelected ? 'fill-accent-hover' : 'fill-accent group-hover:fill-accent-hover group-focus:fill-accent-hover'} x={point.value < 0 ? baseline - width : baseline} y={y} width={width} height={BAR_HEIGHT} />
                  {hasNegative && <line x1={baseline} x2={baseline} y1={y} y2={y + BAR_HEIGHT} stroke="var(--color-muted)" />}
                  <text className={`${labelClasses} fill-heading!`} x={LABEL_WIDTH + barAreaWidth + 12} y={y + 22}>{point.value.toLocaleString('vi-VN')}</text>
                </g>
              )
            })}
          </svg>
        </div>
      </DataState>}
    </section>
  )
}
