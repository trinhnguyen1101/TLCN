import type { DashboardMetadata, Pollutant } from '../types'
import { BASIC_POLLUTANTS, METRIC_META } from '../model/dashboardSelectors'

export function PollutantMetricCard({ pollutant, value, unit, selected, onSelect }: { pollutant: Pollutant; value: number | null; unit: string; selected: boolean; onSelect: () => void }) {
  return <button type="button" disabled={value === null} onClick={onSelect} aria-pressed={selected} className="group min-w-0 cursor-pointer rounded-xl border border-border bg-surface p-3 text-left shadow-control wrap-anywhere transition-[border-color,background-color,box-shadow] enabled:hover:border-accent-border enabled:hover:bg-accent-soft/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-default aria-pressed:border-accent aria-pressed:bg-accent-soft aria-pressed:ring-1 aria-pressed:ring-accent/20 motion-reduce:transition-none">
    <span className="block text-xs font-medium text-secondary group-aria-pressed:text-accent">{METRIC_META[pollutant].label}</span>
    <strong className="mt-1 block text-lg font-semibold text-heading tabular-nums">{value === null ? '—' : value.toLocaleString('vi-VN', { maximumFractionDigits: unit === '1' ? 3 : 1 })}</strong>
    <span className="block text-[.7rem] text-muted">{value === null ? 'Chưa có dữ liệu' : unit}</span>
  </button>
}

export function PollutantMetrics({ metrics, metadata, selected, onSelect, pollutants = BASIC_POLLUTANTS }: { metrics: Record<Pollutant, number | null>; metadata?: DashboardMetadata['metrics']; selected: Pollutant; onSelect: (pollutant: Pollutant) => void; pollutants?: Pollutant[] }) {
  return <div className="grid grid-cols-2 gap-2" aria-label="Nồng độ các chất ô nhiễm">
    {pollutants.map((pollutant) => <PollutantMetricCard key={pollutant} pollutant={pollutant} value={metrics[pollutant]} unit={metadata?.[pollutant]?.unit ?? METRIC_META[pollutant].unit} selected={selected === pollutant} onSelect={() => onSelect(pollutant)} />)}
  </div>
}
