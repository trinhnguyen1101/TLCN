import type { DashboardMetadata, Pollutant } from '../../types/dashboard'
import { BASIC_POLLUTANTS, METRIC_META } from '../../services/dashboardSelectors'

export function PollutantMetricCard({ pollutant, value, unit, selected, onSelect }: { pollutant: Pollutant; value: number | null; unit: string; selected: boolean; onSelect: () => void }) {
  return <button type="button" disabled={value === null} onClick={onSelect} aria-pressed={selected} className="min-w-0 disabled:cursor-default rounded-lg border border-border bg-surface p-3 text-left focus-visible:outline-2 focus-visible:outline-accent aria-pressed:border-accent-border aria-pressed:bg-accent-soft">
    <span className="block text-xs font-medium text-muted">{METRIC_META[pollutant].label}</span>
    <strong className="mt-1 block text-lg font-semibold text-heading tabular-nums">{value === null ? '—' : value.toLocaleString('vi-VN', { maximumFractionDigits: unit === '1' ? 3 : 1 })}</strong>
    <span className="block text-[.7rem] text-muted">{value === null ? 'Chưa có dữ liệu' : unit}</span>
  </button>
}

export function PollutantMetrics({ metrics, metadata, selected, onSelect, pollutants = BASIC_POLLUTANTS }: { metrics: Record<Pollutant, number | null>; metadata?: DashboardMetadata['metrics']; selected: Pollutant; onSelect: (pollutant: Pollutant) => void; pollutants?: Pollutant[] }) {
  return <div className="grid grid-cols-2 gap-2" aria-label="Nồng độ các chất ô nhiễm">
    {pollutants.map((pollutant) => <PollutantMetricCard key={pollutant} pollutant={pollutant} value={metrics[pollutant]} unit={metadata?.[pollutant]?.unit ?? METRIC_META[pollutant].unit} selected={selected === pollutant} onSelect={() => onSelect(pollutant)} />)}
  </div>
}
