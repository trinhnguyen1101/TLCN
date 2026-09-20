import type { ProvinceSnapshot } from '../../types/dashboard'
import './dashboardComponents.css'

export type ComparisonDimension = 'province' | 'year'

export interface ComparisonValue {
  dimension: ComparisonDimension
  provinceCode: string
  year: number
}

interface ComparisonPanelProps {
  value: ComparisonValue
  provinces: ProvinceSnapshot[]
  currentLabel: string
  comparisonLabel: string
  currentValue: number | null
  comparisonValue: number | null
  unit: string
  onChange: (value: ComparisonValue) => void
}

export function ComparisonPanel({ value, provinces, currentLabel, comparisonLabel, currentValue, comparisonValue, unit, onChange }: ComparisonPanelProps) {
  const difference = currentValue !== null && comparisonValue !== null && comparisonValue !== 0
    ? ((currentValue - comparisonValue) / comparisonValue) * 100
    : null

  return (
    <section className="comparison-panel" aria-labelledby="comparison-title">
      <div className="control-heading control-heading--compact">
        <div>
          <p className="eyebrow">So sánh</p>
          <h2 id="comparison-title">Đối chiếu dữ liệu</h2>
        </div>
        <div className="segmented-control" role="group" aria-label="Chiều so sánh">
          <button type="button" className={value.dimension === 'province' ? 'is-active' : ''} onClick={() => onChange({ ...value, dimension: 'province' })}>Tỉnh</button>
          <button type="button" className={value.dimension === 'year' ? 'is-active' : ''} onClick={() => onChange({ ...value, dimension: 'year' })}>Năm</button>
        </div>
      </div>

      <div className="comparison-content">
        <label>
          So sánh với
          {value.dimension === 'province' ? (
            <select value={value.provinceCode} onChange={(event) => onChange({ ...value, provinceCode: event.target.value })}>
              {provinces.map((province) => <option key={province.provinceCode} value={province.provinceCode}>{province.provinceName}</option>)}
            </select>
          ) : (
            <select value={value.year} onChange={(event) => onChange({ ...value, year: Number(event.target.value) })}>
              <option value="2025">2025</option>
              <option value="2026">2026</option>
            </select>
          )}
        </label>
        <div className="comparison-result" aria-live="polite">
          {difference === null ? <p>Chưa có dữ liệu để so sánh.</p> : (
            <>
              <div><span>{currentLabel}</span><strong>{currentValue?.toFixed(1)} {unit}</strong></div>
              <span className="comparison-vs">vs</span>
              <div><span>{comparisonLabel}</span><strong>{comparisonValue?.toFixed(1)} {unit}</strong></div>
              <p className={difference > 0 ? 'trend-up' : difference < 0 ? 'trend-down' : 'trend-neutral'}>
                {difference > 0 ? '↑' : difference < 0 ? '↓' : '→'} {Math.abs(difference).toFixed(1)}%
              </p>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
