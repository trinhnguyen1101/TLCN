import type { ChartPoint } from '../dashboard/types'
import type { ObservationContext } from '../dashboard/model/observationInsights'
import { formatObservationTime } from '../../utils/dates'
import { Button } from '../../components/ui/Button'
import { chartTextWidth, wrapChartText } from './chartLayout'

interface Props {
  chartId: string
  width: number
  point: ChartPoint
  metricLabel: string
  unit: string
  resolution: '3h' | 'daily' | 'monthly'
  context?: ObservationContext
  onExpand?: () => void
}
const number = (value: number) => value.toLocaleString('vi-VN', Math.abs(value) >= 1e9
  ? { notation: 'scientific', maximumFractionDigits: 3 }
  : { maximumFractionDigits: value !== 0 && Math.abs(value) < 1 ? 6 : 3 })

/** One observation has a magnitude and spatial context, but no temporal slope. */
export function SingleObservationChart({ chartId, width, point, metricLabel, unit, resolution, context, onExpand }: Props) {
  const sideBySide = width >= 620
  const heroWidth = sideBySide ? width * .38 : width - 32
  const label = resolution === '3h' ? 'Giá trị tại thời điểm đã chọn' : resolution === 'daily' ? 'Trung bình ngày' : 'Trung bình tháng'
  const date = formatObservationTime(point.timestamp ?? point.label, resolution)
  const value = number(point.value)
  const fontSize = Math.min(44, Math.max(20, heroWidth / (value.length * .65)))
  const heading = wrapChartText(metricLabel, heroWidth)
  const valueY = 44 + (heading.length - 1) * 16 + fontSize + 12
  const dateY = valueY + 45
  const infoY = dateY + 30
  const limit = sideBySide ? 5 : 3
  let shown = context?.regions.slice(0, limit) ?? []
  if (context?.selected && !shown.some((region) => region.id === context.selected!.id)) shown = [...shown.slice(0, limit - 1), context.selected]
  const barLeft = sideBySide ? heroWidth + 50 : 16
  const barWidth = width - barLeft - 16
  const barTop = sideBySide ? 16 : infoY + (context?.selected ? 72 : 42)
  const rows = shown.map((region) => {
    const lines = wrapChartText(`${region.rank}. ${region.label}`, Math.max(50, barWidth - chartTextWidth(number(region.value)) - 18))
    return { ...region, lines, height: Math.max(44, lines.length * 16 + 24) }
  })
  const bars = rows.map((region, index) => ({ ...region, y: barTop + 44 + rows.slice(0, index).reduce((sum, row) => sum + row.height, 0) }))
  const nextY = barTop + 44 + rows.reduce((sum, row) => sum + row.height, 0)
  const min = Math.min(0, ...shown.map((region) => region.value)), max = Math.max(0, ...shown.map((region) => region.value))
  const scale = (value: number) => barLeft + ((value - min) / (max - min || 1)) * barWidth
  const height = Math.max(infoY + (context?.selected ? 76 : 48), bars.length ? nextY + 16 : 0)
  const difference = context?.difference
  const insight = context?.selected && difference !== null && difference !== undefined && context.regions.length > 1
    ? `${context.selected.label} ${Math.abs(difference) < 1e-9 ? 'bằng trung bình' : `${difference > 0 ? 'cao hơn' : 'thấp hơn'} trung bình ${number(Math.abs(difference))}${unit ? ` ${unit}` : ''}`} của ${context.regions.length} vùng có dữ liệu trong cùng ${resolution === '3h' ? 'mốc quan sát' : 'kỳ'}.`
    : context?.highest && context.lowest && context.regions.length > 1
      ? `Cao nhất: ${context.highest.label} (${number(context.highest.value)} ${unit}). Thấp nhất: ${context.lowest.label} (${number(context.lowest.value)} ${unit}).`
      : 'Dữ liệu hiện chỉ có một thời điểm. Mở rộng khoảng thời gian để xem giá trị thay đổi như thế nào.'

  return <div data-chart-mode="single-observation">
    <svg id={chartId} className="block h-auto w-full" viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`${metricLabel}. 1 điểm dữ liệu. ${label}: ${value} ${unit}. ${date}. ${insight}`} fontFamily="Arial, sans-serif">
      <desc>{insight} Chỉ có dữ liệu tại một thời điểm nên chưa thể xác định xu hướng.</desc>
      <rect width={width} height={height} fill="var(--color-surface)" />
      <text x="16" y="20" fontSize="11" fontWeight="600" fill="var(--color-accent)">{label}</text>
      <text x="16" y="44" fontSize="13" fill="var(--color-secondary)">{heading.map((line, index) => <tspan key={index} x="16" dy={index ? 16 : 0}>{line}</tspan>)}</text>
      <text x="16" y={valueY} fontSize={fontSize} fontWeight="700" fill="var(--color-heading)">{value}</text>
      <text x="16" y={valueY + 23} fontSize="13" fill="var(--color-muted)">{unit}</text>
      <text x="16" y={dateY + 5} fontSize="12" fill="var(--color-heading)">{date}</text>
      {context && <>
        <text x="16" y={infoY + 5} fontSize="11" fill="var(--color-muted)">{context.selected ? 'Trung bình các vùng có dữ liệu' : 'Phạm vi so sánh'}</text>
        <text x="16" y={infoY + 28} fontSize="17" fontWeight="600" fill="var(--color-heading)">{context.selected && context.average !== null ? `${number(context.average)} ${unit}` : `${context.regions.length}/${context.totalRegions} vùng có dữ liệu`}</text>
        {context.selected && <text x="16" y={infoY + 53} fontSize="12" fill="var(--color-accent)">Hạng {context.selected.rank}/{context.regions.length} theo giá trị</text>}
      </>}
      {bars.length > 0 && <>
        <text x={barLeft} y={barTop + 4} fontSize="12" fontWeight="600" fill="var(--color-heading)">So sánh cùng {resolution === '3h' ? 'mốc' : 'kỳ'}</text>
        <text x={barLeft} y={barTop + 23} fontSize="10" fill="var(--color-muted)">{context?.selected ? 'Các vùng cao nhất và vùng đang chọn' : `${Math.min(limit, context?.regions.length ?? 0)} vùng có giá trị cao nhất`}</text>
        {bars.map((region) => {
          const selected = region.id === context?.selected?.id
          const barY = region.y + region.lines.length * 16 + 4
          return <g key={region.id}>
            <title>{region.label}: {number(region.value)} {unit}. Hạng {region.rank}.</title>
            <text x={barLeft} y={region.y + 12} fontSize="11" fontWeight={selected ? '700' : '400'} fill={selected ? 'var(--color-accent)' : 'var(--color-heading)'}>{region.lines.map((line, index) => <tspan key={index} x={barLeft} dy={index ? 16 : 0}>{line}</tspan>)}</text>
            <text x={width - 16} y={region.y + 12} textAnchor="end" fontSize="11" fontWeight="600" fill="var(--color-heading)">{number(region.value)}</text>
            <rect x={barLeft} y={barY} width={barWidth} height="8" rx="4" fill="var(--color-surface-subtle)" />
            {min < 0 && <line x1={scale(0)} x2={scale(0)} y1={barY - 2} y2={barY + 10} stroke="var(--color-border-strong)" />}
            <rect x={Math.min(scale(0), scale(region.value))} y={barY} width={Math.max(1, Math.abs(scale(region.value) - scale(0)))} height="8" rx="4" fill={selected ? 'var(--color-accent)' : 'var(--color-accent-border)'} />
          </g>
        })}
      </>}
    </svg>
    <p className="mt-2 rounded-lg border border-accent-border bg-accent-soft px-3 py-2.5 text-xs leading-relaxed text-heading">{insight}</p>
    <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-muted"><p>Chỉ có một thời điểm nên chưa thể xác định xu hướng.</p>{onExpand && <Button onClick={onExpand}>{resolution === 'monthly' ? 'Xem xu hướng 12 tháng' : 'Xem xu hướng 7 ngày'}</Button>}</div>
  </div>
}
