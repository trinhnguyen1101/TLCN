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
  onPointSelect?: (point: ChartPoint) => void
}
const WIDTH = 760,
  HEIGHT = 280
const PADDING = { top: 22, right: 24, bottom: 45, left: 70 }
const format = (value: number) => value.toLocaleString('vi-VN', { maximumFractionDigits: 3 })

export function TrendChart({
  dataReady = true,
  loading = false,
  title,
  description,
  points,
  metricLabel,
  unit,
  fileName,
  onPointSelect,
}: TrendChartProps) {
  const chartId = `trend-${useId().replaceAll(':', '')}`
  const [activeIndex, setActiveIndex] = useState<number | null>(null)
  const geometry = useMemo(() => {
    const values = points.map((point) => point.value).filter((value): value is number => value !== null)
    if (!values.length) return null
    const rawMin = Math.min(...values),
      rawMax = Math.max(...values)
    const range = Math.max(rawMax - rawMin, unit === '1' ? 0.01 : 0.1)
    const min = rawMin < 0 ? rawMin - range * 0.15 : Math.max(0, rawMin - range * 0.15)
    const max = rawMax + range * 0.15
    const ordinals = points.map((point, index) =>
      point.date ? Number(point.date.slice(0, 4)) * 12 + Number(point.date.slice(5, 7)) : index,
    )
    const first = ordinals[0],
      span = ordinals.at(-1)! - first
    const coordinates = points.map((point, index) => ({
      x:
        PADDING.left +
        (span ? (ordinals[index] - first) / span : 0.5) * (WIDTH - PADDING.left - PADDING.right),
      y:
        point.value === null
          ? null
          : PADDING.top + ((max - point.value) / (max - min)) * (HEIGHT - PADDING.top - PADDING.bottom),
    }))
    const path = coordinates
      .map((point, index) =>
        point.y === null
          ? ''
          : `${index === 0 || coordinates[index - 1].y === null || ordinals[index] - ordinals[index - 1] > 1 ? 'M' : 'L'} ${point.x} ${point.y}`,
      )
      .join(' ')
    return { min, max, coordinates, path }
  }, [points, unit])
  return (
    <section
      className="flex min-w-0 flex-col justify-between overflow-hidden rounded-card border border-border bg-surface shadow-card"
      aria-labelledby={`${chartId}-title`}
      aria-busy={loading}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 px-6 pt-6 pb-5 max-[680px]:p-5">
        <div>
          <h2 id={`${chartId}-title`} className="text-[.98rem] font-semibold text-heading">
            Xu hướng theo thời gian
          </h2>
          <p className="mt-[7px] text-[.78rem] text-muted">
            {title} · {unit}
          </p>
          <p className="mt-2 text-xs text-muted">{description}</p>
        </div>
        <ExportActions
          chartId={chartId}
          fileName={fileName}
          csvRows={points.map((point) => ({
            Thoi_gian: point.date ?? point.label,
            [metricLabel]: point.value,
            Don_vi: unit,
          }))}
        />
      </div>
      <div className="grid min-h-[300px] content-center">
        {!dataReady || loading ? (
          <DashboardSkeleton variant="chart" loading={loading} />
        ) : (
          <DataState isEmpty={!geometry} emptyMessage="Không có dữ liệu trong phạm vi đang chọn.">
            {geometry && (
              <div className="overflow-x-auto px-4 pt-2 pb-[18px] max-[680px]:px-2">
              <svg
                id={chartId}
                className="block h-auto w-full min-w-[460px]"
                viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                role="group"
                aria-label={`${title}. ${points.filter((point) => point.value !== null).length} điểm dữ liệu.`}
                fontFamily="Arial, sans-serif"
                fontSize="11"
                fill="#a3b2c7"
              >
                <desc>{description}</desc>
                <rect width={WIDTH} height={HEIGHT} fill="#111c2e" />
                {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                  const y = PADDING.top + ratio * (HEIGHT - PADDING.top - PADDING.bottom)
                  return (
                    <g key={ratio}>
                      <line
                        x1={PADDING.left}
                        x2={WIDTH - PADDING.right}
                        y1={y}
                        y2={y}
                        stroke="#2b3b53"
                        strokeDasharray="4 4"
                      />
                      <text x={PADDING.left - 9} y={y + 4} textAnchor="end">
                        {format(geometry.max - ratio * (geometry.max - geometry.min))}
                      </text>
                    </g>
                  )
                })}
                <path
                  d={geometry.path}
                  fill="none"
                  stroke="#5eead4"
                  strokeWidth="2.5"
                  strokeLinejoin="round"
                />
                {geometry.coordinates.map((coordinate, index) =>
                  coordinate.y === null ? null : (
                    <g
                      key={points[index].date ?? index}
                      onMouseEnter={() => setActiveIndex(index)}
                      onMouseLeave={() => setActiveIndex(null)}
                      onFocus={() => setActiveIndex(index)}
                      onBlur={() => setActiveIndex(null)}
                      tabIndex={0}
                      role={onPointSelect ? 'button' : 'img'}
                      aria-label={`${points[index].label}: ${format(points[index].value!)} ${unit}${onPointSelect ? '. Xem tháng này' : ''}`}
                      onClick={() => onPointSelect?.(points[index])}
                      onKeyDown={(event) => {
                        if (onPointSelect && (event.key === 'Enter' || event.key === ' ')) {
                          event.preventDefault()
                          onPointSelect(points[index])
                        }
                      }}
                      style={{ cursor: onPointSelect ? 'pointer' : 'default' }}
                    >
                      <circle cx={coordinate.x} cy={coordinate.y} r="12" fill="transparent" />
                      <circle
                        cx={coordinate.x}
                        cy={coordinate.y}
                        r={activeIndex === index ? 5 : 3.5}
                        fill="#111c2e"
                        stroke="#5eead4"
                        strokeWidth="2"
                      />
                      <title>
                        {points[index].label}: {format(points[index].value!)} {unit}
                      </title>
                      {activeIndex === index && (
                        <g className="pointer-events-none">
                          <rect
                            x={Math.max(4, Math.min(coordinate.x - 100, WIDTH - 204))}
                            y={Math.max(4, coordinate.y - 48)}
                            width="200"
                            height="36"
                            rx="7"
                            fill="#203149"
                          />
                          <text
                            x={Math.max(104, Math.min(coordinate.x, WIDTH - 104))}
                            y={Math.max(27, coordinate.y - 25)}
                            textAnchor="middle"
                            fill="#f8fafc"
                          >
                            {points[index].label}: {format(points[index].value!)} {unit}
                          </text>
                        </g>
                      )}
                    </g>
                  ),
                )}
                {points.map((point, index) =>
                  points.length > 12 &&
                  index % Math.ceil(points.length / 12) !== 0 &&
                  index !== points.length - 1 ? null : (
                    <text
                      key={point.date ?? index}
                      x={geometry.coordinates[index].x}
                      y={HEIGHT - 17}
                      textAnchor="middle"
                    >
                      {point.label}
                    </text>
                  ),
                )}
              </svg>
              </div>
            )}
          </DataState>
        )}
      </div>
    </section>
  )
}
