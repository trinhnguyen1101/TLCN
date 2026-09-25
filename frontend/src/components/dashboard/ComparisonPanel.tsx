import { DashboardSkeleton } from './DashboardSkeleton'
import type { ProvinceSnapshot } from '../../types/dashboard'
import { Button, SegmentedControl } from '../ui/Button'
import { Field, Select } from '../ui/FormControls'

type ComparisonDimension = 'province' | 'year'

export interface ComparisonValue {
  dimension: ComparisonDimension
  provinceCode: string
  year: number
}

interface ComparisonPanelProps {
  years: number[]
  dataReady?: boolean
  loading?: boolean
  value: ComparisonValue
  provinces: ProvinceSnapshot[]
  currentLabel: string
  comparisonLabel: string
  currentValue: number | null
  comparisonValue: number | null
  unit: string
  onChange: (value: ComparisonValue) => void
}

export function ComparisonPanel({ years, dataReady = true, loading = false, value, provinces, currentLabel, comparisonLabel, currentValue, comparisonValue, unit, onChange }: ComparisonPanelProps) {
  const difference = currentValue !== null && comparisonValue !== null && comparisonValue !== 0
    ? ((currentValue - comparisonValue) / Math.abs(comparisonValue)) * 100
    : null

  return (
    <section className="min-w-0 rounded-card border border-border bg-surface px-6 py-[22px] shadow-card max-[480px]:p-5" aria-labelledby="comparison-title">
      <div className="mb-[18px] flex flex-wrap items-center justify-between gap-3 max-[480px]:gap-3.5">
        <h2 id="comparison-title" className="text-[.98rem] font-semibold text-heading">So sánh dữ liệu</h2>
        <SegmentedControl aria-label="Chiều so sánh">
          <Button variant="segment" aria-pressed={value.dimension === 'province'} onClick={() => onChange({ ...value, dimension: 'province' })}>Theo tỉnh</Button>
          <Button variant="segment" aria-pressed={value.dimension === 'year'} onClick={() => onChange({ ...value, dimension: 'year' })}>Theo năm</Button>
        </SegmentedControl>
      </div>

      <div className="grid gap-[18px]">
        <Field inline>
          So sánh với
          {value.dimension === 'province' ? (
            <Select disabled={!dataReady || provinces.length === 0} value={value.provinceCode} onChange={(event) => onChange({ ...value, provinceCode: event.target.value })}>
              {!dataReady && <option value={value.provinceCode}>Danh sách tỉnh chưa sẵn sàng</option>}
              {provinces.map((province) => <option key={province.provinceCode} value={province.provinceCode}>{province.provinceName}</option>)}
            </Select>
          ) : (
            <Select disabled={!dataReady || years.length === 0} value={value.year} onChange={(event) => onChange({ ...value, year: Number(event.target.value) })}>
              {years.map((year) => <option key={year} value={year}>{year}</option>)}
            </Select>
          )}
        </Field>
        {!dataReady ? <DashboardSkeleton variant="comparison" loading={loading} /> : (
          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 max-[480px]:gap-3" aria-live="polite">
            {currentValue === null || comparisonValue === null ? <p className="col-span-full py-[22px] text-[.83rem] text-muted">Chưa có dữ liệu để so sánh.</p> : (
              <>
                <div className="grid min-w-0 gap-[7px]"><span className="text-[.78rem] wrap-anywhere text-muted">{currentLabel}</span><strong className="text-[1.55rem] font-semibold tracking-[-.025em] text-ink tabular-nums max-[480px]:text-[1.3rem]">{currentValue?.toFixed(unit === '1' ? 3 : 1)} <small className="inline-block text-[.75rem] font-normal tracking-normal text-muted">{unit}</small></strong></div>
                <span className="text-[1.4rem] font-light text-muted">/</span>
                <div className="grid min-w-0 gap-[7px]"><span className="text-[.78rem] wrap-anywhere text-muted">{comparisonLabel}</span><strong className="text-[1.55rem] font-semibold tracking-[-.025em] text-ink tabular-nums max-[480px]:text-[1.3rem]">{comparisonValue?.toFixed(unit === '1' ? 3 : 1)} <small className="inline-block text-[.75rem] font-normal tracking-normal text-muted">{unit}</small></strong></div>
                <div className="col-span-full flex min-w-0 items-center justify-between gap-3 border-t border-border pt-3.5">
                  <span className="text-[.78rem] wrap-anywhere text-muted">Chênh lệch so với {comparisonLabel}</span>
                  <p className={`shrink-0 rounded-md px-2 py-[5px] text-[.78rem] font-semibold tabular-nums ${difference !== null && difference > 0 ? 'bg-danger-soft text-danger' : difference !== null && difference < 0 ? 'bg-success-soft text-success' : 'bg-surface-subtle text-secondary'}`}>
                    {difference === null ? '— (mốc bằng 0)' : `${difference > 0 ? '↑' : difference < 0 ? '↓' : '→'} ${Math.abs(difference).toFixed(1)}%`}
                  </p>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
