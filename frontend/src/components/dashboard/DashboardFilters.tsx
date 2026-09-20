import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../types/dashboard'
import './dashboardComponents.css'

interface DashboardFiltersProps {
  value: DashboardFiltersValue
  provinces: ProvinceSnapshot[]
  sectors: string[]
  onChange: (value: DashboardFiltersValue) => void
  onReset: () => void
}

const pollutantOptions: Array<{ value: Pollutant; label: string }> = [
  { value: 'pm25', label: 'PM2.5' },
  { value: 'pm10', label: 'PM10' },
  { value: 'o3', label: 'O₃' },
  { value: 'no2', label: 'NO₂' },
  { value: 'so2', label: 'SO₂' },
  { value: 'co', label: 'CO' },
]

export function DashboardFilters({ value, provinces, sectors, onChange, onReset }: DashboardFiltersProps) {
  const update = <K extends keyof DashboardFiltersValue>(key: K, nextValue: DashboardFiltersValue[K]) => {
    onChange({ ...value, [key]: nextValue })
  }

  return (
    <section className="dashboard-filters" aria-labelledby="filter-title">
      <div className="control-heading">
        <div>
          <p className="eyebrow">Bộ lọc chung</p>
          <h2 id="filter-title">Phạm vi dữ liệu</h2>
        </div>
        <button className="button button--secondary" type="button" onClick={onReset}>Đặt lại bộ lọc</button>
      </div>

      <div className="filter-grid">
        <label>
          Tỉnh / thành
          <select value={value.provinceCode} onChange={(event) => update('provinceCode', event.target.value as DashboardFiltersValue['provinceCode'])}>
            <option value="all">Toàn quốc</option>
            {provinces.map((province) => <option key={province.provinceCode} value={province.provinceCode}>{province.provinceName}</option>)}
          </select>
        </label>
        <label>
          Chất ô nhiễm
          <select value={value.pollutant} onChange={(event) => update('pollutant', event.target.value as Pollutant)}>
            {pollutantOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          Năm
          <select value={value.year} onChange={(event) => update('year', event.target.value === 'all' ? 'all' : Number(event.target.value))}>
            <option value="all">Tất cả</option>
            <option value="2026">2026</option>
            <option value="2025">2025</option>
          </select>
        </label>
        <label>
          Tháng
          <select value={value.month} onChange={(event) => update('month', event.target.value === 'all' ? 'all' : Number(event.target.value))}>
            <option value="all">Tất cả</option>
            {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>Tháng {index + 1}</option>)}
          </select>
        </label>
        <label>
          Từ ngày
          <input type="date" value={value.startDate} max={value.endDate || undefined} onChange={(event) => update('startDate', event.target.value)} />
        </label>
        <label>
          Đến ngày
          <input type="date" value={value.endDate} min={value.startDate || undefined} onChange={(event) => update('endDate', event.target.value)} />
        </label>
        <label>
          Ngành phát thải
          <select value={value.sector} onChange={(event) => update('sector', event.target.value)}>
            <option value="all">Tất cả ngành</option>
            {sectors.map((sector) => <option key={sector} value={sector}>{sector}</option>)}
          </select>
        </label>
      </div>
    </section>
  )
}
