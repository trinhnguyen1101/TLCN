import { useId, useMemo, useState } from 'react'
import { DashboardSkeleton } from '../../components/dashboard/DashboardSkeleton'
import { DataState } from '../../components/dashboard/DataState'
import { ExportActions } from '../../components/dashboard/ExportActions'
import type { ChartPoint } from '../../types/dashboard'

interface TrendChartProps {
  dataReady?: boolean
  loading?: boolean
  title: string
  description: string
  points: ChartPoint[]
  metricLabel: string
  unit: string
  fileName: string
}

const WIDTH = 760
const HEIGHT = 280
const PADDING = { top: 22, right: 24, bottom: 45, left: 56 }

export function TrendChart({ dataReady = true, loading = false, title, description, points, metricLabel, unit, fileName }: TrendChartProps) {
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
    const plotWidth = WIDTH - PADDING.left - PADDING.right
    const plotHeight = HEIGHT - PADDING.top - PADDING.bottom
    const coordinates = points.map((point, index) => ({
      x: PADDING.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
      y: PADDING.top + ((max - point.value) / (max - min)) * plotHeight,
    }))
    return { min, max, coordinates, path: coordinates.map((coordinate, index) => `${index === 0 ? 'M' : 'L'} ${coordinate.x} ${coordinate.y}`).join(' ') }
  }, [points, unit])

  return (
    <section className="flex min-w-0 flex-col justify-between overflow-hidden rounded-card border border-border bg-surface shadow-card" aria-labelledby={`${chartId}-title`}>
      <div className="flex flex-wrap items-start justify-between gap-4 px-6 pt-6 pb-5 max-[680px]:p-5">
        <div>
          <h2 id={`${chartId}-title`} className="text-[.98rem] font-semibold text-heading">Xu hướng theo thời gian</h2>
          <p className="mt-[7px] text-[.78rem] text-muted">{title}</p>
        </div>
        <ExportActions chartId={chartId} fileName={fileName} csvRows={points.map((point) => ({ Thoi_gian: point.label, [metricLabel]: point.value, Don_vi: unit }))} />
      </div>

      {!dataReady ? <DashboardSkeleton variant="chart" loading={loading} /> : (
        <DataState isEmpty={points.length === 0} emptyMessage="Hãy thay đổi tỉnh, năm, tháng hoặc khoảng ngày.">
          {geometry && (
            <div className="overflow-x-auto px-4 pt-2 pb-[18px] max-[680px]:px-2">
              <svg id={chartId} className="block h-auto w-full min-w-[460px]" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${title}. ${points.length} điểm dữ liệu.`} fontFamily="Arial, sans-serif" fontSize="11" fill="#a3b2c7">
                <desc>{description}</desc>
                <defs>
                  <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#2dd4bf" stopOpacity=".18" />
                    <stop offset="100%" stopColor="#2dd4bf" stopOpacity=".01" />
                  </linearGradient>
                </defs>
                <rect width={WIDTH} height={HEIGHT} fill="#111c2e" />
                {[0, .25, .5, .75, 1].map((ratio) => {
                  const y = PADDING.top + ratio * (HEIGHT - PADDING.top - PADDING.bottom)
                  const value = geometry.max - ratio * (geometry.max - geometry.min)
                  return <g key={ratio}><line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} stroke="#2b3b53" strokeDasharray="4 4" /><text x={PADDING.left - 9} y={y + 4} textAnchor="end">{value.toFixed(unit === '1' ? 3 : 1)}</text></g>
                })}
                <path d={`${geometry.path} L ${geometry.coordinates.at(-1)!.x} ${HEIGHT - PADDING.bottom} L ${geometry.coordinates[0].x} ${HEIGHT - PADDING.bottom} Z`} fill={`url(#${gradientId})`} />
                <path d={geometry.path} fill="none" stroke="#5eead4" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
                {geometry.coordinates.map((coordinate, index) => (
                  <g key={`${points[index].label}-${index}`} onMouseEnter={() => setActiveIndex(index)} onMouseLeave={() => setActiveIndex(null)} onFocus={() => setActiveIndex(index)} onBlur={() => setActiveIndex(null)} tabIndex={0} className="focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" role="img" aria-label={`${points[index].label}: ${points[index].value} ${unit}`}>
                    <circle cx={coordinate.x} cy={coordinate.y} r="11" fill="transparent" />
                    <circle cx={coordinate.x} cy={coordinate.y} r={activeIndex === index ? 5 : 3.5} fill="#111c2e" stroke="#5eead4" strokeWidth="2" />
                    {activeIndex === index && (
                      <g className="pointer-events-none">
                        <rect x={Math.max(4, Math.min(coordinate.x - 72, WIDTH - 148))} y={Math.max(4, coordinate.y - 48)} width="144" height="36" rx="7" fill="#203149" />
                        <text x={Math.max(76, Math.min(coordinate.x, WIDTH - 76))} y={Math.max(27, coordinate.y - 25)} textAnchor="middle" fill="#f8fafc" fontSize="11">{points[index].label}: {points[index].value} {unit}</text>
                      </g>
                    )}
                  </g>
                ))}
                {points.map((point, index) => {
                  if (points.length > 12 && index % Math.ceil(points.length / 12) !== 0 && index !== points.length - 1) return null
                  return <text key={`label-${point.label}-${index}`} x={geometry.coordinates[index].x} y={HEIGHT - 17} textAnchor="middle">{point.label}</text>
                })}
                <text x="16" y={HEIGHT / 2} transform={`rotate(-90 16 ${HEIGHT / 2})`} textAnchor="middle" fontSize="11">{metricLabel} ({unit})</text>
              </svg>
            </div>
          )}
        </DataState>
      )}
    </section>
  )
}
