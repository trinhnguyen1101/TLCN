import { useId, useMemo, useState } from 'react'
import { DashboardSkeleton } from '../../components/ui/DashboardSkeleton'
import { DataState } from '../../components/ui/DataState'
import { ExportActions } from '../../components/ui/ExportActions'
import { chartTextWidth, useChartWidth, wrapChartText } from './chartLayout'
import type { ChartPoint } from '../dashboard/types'
import type { ObservationContext } from '../dashboard/model/observationInsights'
import { formatObservationTime } from '../../utils/dates'
import { SingleObservationChart } from './SingleObservationChart'

interface TrendChartProps {
  compact?: boolean
  dataReady?: boolean
  loading?: boolean
  title: string
  description: string
  points: ChartPoint[]
  metricLabel: string
  unit: string
  fileName: string
  resolution?: '3h' | 'daily' | 'monthly'
  observationContext?: ObservationContext
  onExpandPeriod?: () => void
}

export function TrendChart({ compact = false, dataReady = true, loading = false, title, description, points, metricLabel, unit, fileName, resolution = '3h', observationContext, onExpandPeriod }: TrendChartProps) {
  const { containerRef, width } = useChartWidth(760)
  const WIDTH = width
  const metricLines = wrapChartText(`${metricLabel}${unit && ` (${unit})`}`, WIDTH - 16)
  const headingHeight = metricLines.length * 16 + 8
  const HEIGHT = (compact ? 170 : 230) + headingHeight
  const chartId = `trend-${useId().replaceAll(':', '')}`
  const gradientId = `${chartId}-gradient`
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const geometry = useMemo(() => {
    if (points.length === 0) return null
    const values = points.map((point) => point.value)
    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
    const range = Math.max(rawMax - rawMin, unit === '1' ? .01 : 1)
    const min = rawMin < 0 ? rawMin - range * .15 : Math.max(0, rawMin - range * .15)
    const max = rawMax + range * .15
    const ticks = [0, .25, .5, .75, 1].map((ratio) => ({ ratio, label: (max - ratio * (max - min)).toFixed(unit === '1' ? 3 : 1) }))
    const padding = { top: headingHeight + 22, right: 12, bottom: 36, left: Math.max(...ticks.map((tick) => chartTextWidth(tick.label, 11))) + 16 }
    const plotWidth = Math.max(1, WIDTH - padding.left - padding.right)
    const plotHeight = HEIGHT - padding.top - padding.bottom
    const coordinates = points.map((point, index) => ({
      x: padding.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
      y: padding.top + ((max - point.value) / (max - min)) * plotHeight,
    }))
    // Reserve the endpoint labels, then add only labels that fit between them.
    const labels = [0]
    let previousEnd = coordinates[0].x + chartTextWidth(points[0].label, 11)
    const lastIndex = points.length - 1
    const lastStart = coordinates[lastIndex].x - chartTextWidth(points[lastIndex].label, 11)
    for (let index = 1; index < lastIndex; index++) {
      const halfWidth = chartTextWidth(points[index].label, 11) / 2
      if (coordinates[index].x - halfWidth >= previousEnd + 14 && coordinates[index].x + halfWidth <= lastStart - 14) {
        labels.push(index)
        previousEnd = coordinates[index].x + halfWidth
      }
    }
    if (lastIndex > 0) {
      if (lastStart < previousEnd + 14 && labels.length === 1) labels.pop()
      labels.push(lastIndex)
    }
    return { padding, ticks, labels, coordinates, path: coordinates.map((coordinate, index) => `${index === 0 ? 'M' : 'L'} ${coordinate.x} ${coordinate.y}`).join(' ') }
  }, [points, unit, WIDTH, HEIGHT, headingHeight])
  const activePoint = points[activeIndex ?? -1] ?? points.at(-1)

  return (
    <section className="flex min-w-0 flex-col justify-between overflow-hidden rounded-card border border-border bg-surface shadow-card wrap-anywhere" aria-labelledby={`${chartId}-title`}>
      <div className="flex flex-wrap items-start justify-between gap-4 px-4 pt-4 pb-3 max-[680px]:p-5">
        <div className="min-w-0">
          <h2 id={`${chartId}-title`} className="text-[.98rem] font-semibold text-heading">{points.length === 1 && dataReady ? 'Số liệu tại thời điểm đã chọn' : 'Xu hướng theo thời gian'}</h2>
          <p className="mt-[7px] text-[.78rem] text-muted">{title}</p>
        </div>
        <ExportActions chartId={chartId} fileName={fileName} csvRows={points.map((point) => ({ Thoi_gian_UTC: point.timestamp ?? point.label, [metricLabel]: point.value, Don_vi: unit }))} />
      </div>
      <p className="px-6 pb-3 text-xs text-muted">{description}</p>

      <div ref={containerRef} className="px-4 pt-2 pb-[18px] max-[680px]:px-2">
      {!dataReady ? <DashboardSkeleton variant="chart" loading={loading} /> : (
        <DataState isEmpty={points.length === 0} emptyMessage="Hãy chọn khu vực hoặc khoảng thời gian khác để xem dữ liệu.">
          {points.length === 1 ? <SingleObservationChart chartId={chartId} width={WIDTH} point={points[0]} metricLabel={metricLabel} unit={unit} resolution={resolution} context={observationContext} onExpand={onExpandPeriod} /> : geometry && (
            <>
              <svg id={chartId} className="block h-auto w-full" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={`${title}. ${points.length} điểm dữ liệu. ${metricLabel} (${unit})`} fontFamily="Arial, sans-serif" fontSize="11" fill="var(--color-muted)">
                <desc>{description} {metricLabel} ({unit})</desc>
                <defs>
                  <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-accent)" stopOpacity=".18" />
                    <stop offset="100%" stopColor="var(--color-accent)" stopOpacity=".01" />
                  </linearGradient>
                </defs>
                <rect width={WIDTH} height={HEIGHT} fill="var(--color-surface)" />
                <text x="8" y="14" fontSize="12" fontWeight="500" fill="var(--color-secondary)">{metricLines.map((line, index) => <tspan key={index} x="8" dy={index ? 16 : 0}>{line}</tspan>)}</text>
                {geometry.ticks.map(({ ratio, label }) => {
                  const y = geometry.padding.top + ratio * (HEIGHT - geometry.padding.top - geometry.padding.bottom)
                  return <g key={ratio}><line x1={geometry.padding.left} x2={WIDTH - geometry.padding.right} y1={y} y2={y} stroke="var(--color-border)" strokeDasharray="4 4" /><text x={geometry.padding.left - 9} y={y + 4} textAnchor="end">{label}</text></g>
                })}
                <path d={`${geometry.path} L ${geometry.coordinates.at(-1)!.x} ${HEIGHT - geometry.padding.bottom} L ${geometry.coordinates[0].x} ${HEIGHT - geometry.padding.bottom} Z`} fill={`url(#${gradientId})`} />
                <path d={geometry.path} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
                {geometry.coordinates.map((coordinate, index) => (
                  <g key={`${points[index].label}-${index}`} onMouseEnter={() => setActiveIndex(index)} onMouseLeave={() => setActiveIndex(null)} onFocus={() => setActiveIndex(index)} onBlur={() => setActiveIndex(null)} tabIndex={0} className="focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" role="img" aria-label={`${points[index].label}: ${points[index].value} ${unit}`}>
                    <title>{formatObservationTime(points[index].timestamp ?? points[index].label, resolution)}: {points[index].value} {unit}</title>
                    <circle cx={coordinate.x} cy={coordinate.y} r="11" fill="transparent" />
                    <circle cx={coordinate.x} cy={coordinate.y} r={activeIndex === index ? 5 : points.length > 30 ? 0 : 3.5} fill="var(--color-surface)" stroke="var(--color-accent)" strokeWidth="2" />
                  </g>
                ))}
                {geometry.labels.map((index) => {
                  return <text key={`label-${index}`} x={geometry.coordinates[index].x} y={HEIGHT - 12} textAnchor={points.length === 1 ? 'middle' : index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}>{points[index].label}</text>
                })}
              </svg>
              <p aria-live="polite" aria-atomic="true" className="mt-2 min-h-9 rounded-lg bg-surface-subtle px-3 py-2 text-xs leading-relaxed text-heading">{activePoint && <>{formatObservationTime(activePoint.timestamp ?? activePoint.label, resolution)} · {activePoint.value.toLocaleString('vi-VN', { maximumFractionDigits: 6 })} {unit}</>}</p>
            </>
          )}
        </DataState>
      )}
      </div>
    </section>
  )
}
