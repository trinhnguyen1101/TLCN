import { useId } from 'react'
import { DashboardSkeleton } from '../../components/ui/DashboardSkeleton'
import { DataState } from '../../components/ui/DataState'
import { ExportActions } from '../../components/ui/ExportActions'
import { chartTextWidth, useChartWidth, wrapChartText } from './chartLayout'

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

const labelClasses = 'fill-muted text-[12px] font-medium'

const BAR_HEIGHT = 34
const ROW_GAP = 18
const TOP = 12

export function HorizontalBarChart({ compact = false, dataReady = true, loading = false, eyebrow, title, description, points, unit, fileName, selectedId, onSelect }: HorizontalBarChartProps) {
  const chartId = `bars-${useId().replaceAll(':', '')}`
  const { containerRef, width: WIDTH } = useChartWidth(560)
  const stackedValue = WIDTH < 420
  const labelWidth = Math.min(220, WIDTH * (stackedValue ? .43 : .35))
  const valueWidth = stackedValue ? 8 : Math.max(...points.map((point) => chartTextWidth(point.value.toLocaleString('vi-VN'))), 40) + 20
  const barAreaWidth = Math.max(1, WIDTH - labelWidth - valueWidth)
  const maxValue = Math.max(...points.map((point) => Math.abs(point.value)), 1)
  const hasNegative = points.some((point) => point.value < 0)
  const layout = points.reduce((layout, point, index) => {
    const lines = wrapChartText(`${index + 1}. ${point.label}`, labelWidth - 14)
    const rowHeight = Math.max(lines.length * 16, BAR_HEIGHT + (stackedValue ? 20 : 0))
    return { rows: [...layout.rows, { point, lines, y: layout.nextY, rowHeight }], nextY: layout.nextY + rowHeight + ROW_GAP }
  }, { rows: [] as Array<{ point: HorizontalBarPoint; lines: string[]; y: number; rowHeight: number }>, nextY: TOP })
  const height = Math.max(100, layout.nextY - ROW_GAP + TOP)

  return (
    <section className="min-w-0 overflow-hidden rounded-card border border-border bg-surface shadow-card wrap-anywhere" aria-labelledby={`${chartId}-title`}>
      <div className="flex items-start justify-between gap-4 px-4 pt-4 pb-1 [@media(max-width:620px)]:flex-col">
        <div className="min-w-0">
          <p className="text-xs text-muted">{eyebrow}</p>
          <h2 id={`${chartId}-title`} className="mt-1 text-[1.02rem] font-semibold text-heading">{title}</h2>
        </div>
        <ExportActions
          chartId={chartId}
          fileName={fileName}
          csvRows={points.map((point, index) => ({ Hang: index + 1, Ten: point.label, Gia_tri: point.value, Don_vi: unit }))}
        />
      </div>
      <p className="px-4 pt-2 pb-1 text-xs text-muted">Đơn vị: {unit || 'Không có đơn vị'}</p>

      <div ref={containerRef} className={`px-3 pt-1 pb-3 ${compact ? 'max-h-[360px] overflow-y-auto' : ''}`}>
      {!dataReady ? <DashboardSkeleton variant="chart" loading={loading} /> : <DataState isEmpty={points.length === 0} emptyMessage="Không có dữ liệu xếp hạng theo bộ lọc hiện tại.">
          <svg id={chartId} className="block h-auto w-full min-w-0" viewBox={`0 0 ${WIDTH} ${height}`} fontFamily="Arial, sans-serif" role="img" aria-label={`${title}. ${points.length} mục dữ liệu. Đơn vị: ${unit}`}><desc>{description} Đơn vị: {unit}</desc>
            <rect className="fill-surface" width={WIDTH} height={height} />
            {layout.rows.map(({ point, lines, y: rowY, rowHeight }) => {
              const y = rowY + (rowHeight - BAR_HEIGHT - (stackedValue ? 20 : 0)) / 2
              const width = Math.max(0, (Math.abs(point.value) / maxValue) * barAreaWidth / (hasNegative ? 2 : 1))
              const baseline = labelWidth + (hasNegative ? barAreaWidth / 2 : 0)
              const isSelected = selectedId === point.id
              return (
                <g
                  key={point.id}
                  className={onSelect ? 'group cursor-pointer focus:outline-none' : undefined}
                  tabIndex={onSelect ? 0 : undefined}
                  role={onSelect ? 'button' : undefined}
                  aria-label={`${point.label}: ${point.value.toLocaleString('vi-VN')} ${unit}${onSelect ? '. Nhấn để lọc dữ liệu.' : ''}`}
                  onClick={() => onSelect?.(point)}
                  onKeyDown={(event) => {
                    if (onSelect && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault()
                      onSelect(point)
                    }
                  }}
                >
                  <title>{point.label}: {point.value.toLocaleString('vi-VN')} {unit}</title>
                  <text className={labelClasses} x={labelWidth - 14} y={rowY + (rowHeight - lines.length * 16) / 2 + 12} textAnchor="end">{lines.map((line, index) => <tspan key={index} x={labelWidth - 14} dy={index ? 16 : 0}>{line}</tspan>)}</text>
                  <rect className={`fill-surface-subtle ${isSelected ? 'stroke-accent stroke-2' : 'stroke-border stroke-1'}`} x={labelWidth} y={y} width={barAreaWidth} height={BAR_HEIGHT} />
                  <rect className={isSelected ? 'fill-accent-hover' : 'fill-accent group-hover:fill-accent-hover group-focus:fill-accent-hover'} x={point.value < 0 ? baseline - width : baseline} y={y} width={width} height={BAR_HEIGHT} />
                  {hasNegative && <line x1={baseline} x2={baseline} y1={y} y2={y + BAR_HEIGHT} stroke="var(--color-muted)" />}
                  <text className={`${labelClasses} fill-heading!`} x={WIDTH - 4} y={stackedValue ? y + BAR_HEIGHT + 16 : y + 22} textAnchor="end">{point.value.toLocaleString('vi-VN')}</text>
                </g>
              )
            })}
          </svg>
      </DataState>}
      </div>
    </section>
  )
}
