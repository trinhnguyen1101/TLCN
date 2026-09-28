import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../types/dashboard'
import { DashboardIcon } from './DashboardIcon'
import { Button } from '../ui/Button'
import { DateInput, Field, Select } from '../ui/FormControls'

interface DashboardFiltersProps {
  years: number[]
  pollutantOptions: Array<{ value: Pollutant; label: string }>
  dataReady?: boolean
  value: DashboardFiltersValue
  provinces: ProvinceSnapshot[]
  sectors: string[]
  onChange: (value: DashboardFiltersValue) => void
  onReset: () => void
}

export function DashboardFilters({ years, pollutantOptions, dataReady = true, value, provinces, sectors, onChange, onReset }: DashboardFiltersProps) {
  const update = <K extends keyof DashboardFiltersValue>(key: K, nextValue: DashboardFiltersValue[K]) => {
    onChange({ ...value, [key]: nextValue, ...((key === 'startDate' || key === 'endDate') ? { year: 'all' as const, month: 'all' as const } : {}), ...((key === 'year' || key === 'month') ? { startDate: '', endDate: '' } : {}) })
  }

  return (
    <section className="min-w-0 rounded-card border border-border bg-surface px-6 py-[22px] shadow-card max-[480px]:p-5" aria-labelledby="filter-title">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 max-[480px]:gap-3.5">
        <h2 id="filter-title" className="flex items-center gap-[9px] text-[.98rem] font-semibold text-heading"><DashboardIcon name="filter" className="text-muted" />Bộ lọc</h2>
        <Button onClick={onReset}><DashboardIcon name="reset" size="small" />Đặt lại bộ lọc</Button>
      </div>

      <div className="dashboard-filter-grid grid grid-cols-[1.3fr_1fr_.8fr_.9fr_1.15fr_1.15fr_1.3fr] gap-3.5 max-[1250px]:grid-cols-4 max-[760px]:grid-cols-2 max-[480px]:grid-cols-1">
        <Field>
          Tỉnh / thành
          <Select aria-label="Tỉnh / thành" disabled={!dataReady} value={value.provinceCode} onChange={(event) => update('provinceCode', event.target.value as DashboardFiltersValue['provinceCode'])}>
            <option value="all">Toàn quốc</option>
            {provinces.map((province) => <option key={province.provinceCode} value={province.provinceCode}>{province.provinceName}</option>)}
          </Select>
        </Field>
        <Field>
          Chỉ số
          <Select aria-label="Chỉ số" value={value.pollutant} onChange={(event) => update('pollutant', event.target.value as Pollutant)}>
            {pollutantOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </Field>
        <Field>
          Năm
          <Select aria-label="Năm" value={value.year} onChange={(event) => update('year', event.target.value === 'all' ? 'all' : Number(event.target.value))}>
            <option value="all">Tất cả</option>
            {years.map((year) => <option key={year} value={year}>{year}</option>)}
          </Select>
        </Field>
        <Field>
          Tháng
          <Select aria-label="Tháng" value={value.month} onChange={(event) => update('month', event.target.value === 'all' ? 'all' : Number(event.target.value))}>
            <option value="all">Tất cả</option>
            {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>Tháng {index + 1}</option>)}
          </Select>
        </Field>
        <Field>
          Từ ngày
          <DateInput aria-label="Từ ngày" value={value.startDate} max={value.endDate || undefined} onChange={(event) => update('startDate', event.target.value)} />
        </Field>
        <Field>
          Đến ngày
          <DateInput aria-label="Đến ngày" value={value.endDate} min={value.startDate || undefined} onChange={(event) => update('endDate', event.target.value)} />
        </Field>
        <Field>
          Ngành phát thải
          <Select aria-label="Ngành phát thải" disabled={!dataReady || sectors.length === 0} value={value.sector} onChange={(event) => update('sector', event.target.value)}>
            <option value="all">Tất cả ngành</option>
            {sectors.map((sector) => <option key={sector} value={sector}>{sector}</option>)}
          </Select>
        </Field>
      </div>
      <p className="mt-4 text-xs leading-relaxed text-muted">Dữ liệu theo tháng: khoảng ngày chọn các tháng giao với khoảng đó. Chọn khoảng ngày sẽ bỏ lọc năm/tháng và ngược lại.</p>
      {value.startDate && value.endDate && value.startDate > value.endDate && <p role="alert" className="mt-2 text-xs text-danger">Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.</p>}
    </section>
  )
}
