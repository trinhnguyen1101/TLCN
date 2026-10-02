import { useId, useState } from 'react'
import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../types/dashboard'
import { DashboardIcon } from './DashboardIcon'
import { Button } from '../ui/Button'
import { DateInput, Field, Select } from '../ui/FormControls'

interface DashboardFiltersProps {
  variant?: 'user' | 'admin'
  years: number[]
  pollutantOptions: Array<{ value: Pollutant; label: string }>
  dataReady?: boolean
  value: DashboardFiltersValue
  provinces: ProvinceSnapshot[]
  sectors?: string[]
  onChange: (value: DashboardFiltersValue) => void
  onReset: () => void
}

export function DashboardFilters({ variant = 'admin', years, pollutantOptions, dataReady = true, value, provinces, sectors = [], onChange, onReset }: DashboardFiltersProps) {
  const id = useId()
  const [expanded, setExpanded] = useState(false)
  const [customRange, setCustomRange] = useState(false)
  const update = <K extends keyof DashboardFiltersValue>(key: K, nextValue: DashboardFiltersValue[K]) => onChange({ ...value, [key]: nextValue })
  const period = customRange || value.startDate || value.endDate ? 'custom' : value.year === 'all' ? 'current' : String(value.year)

  return (
    <section className="sticky top-2 z-[600] mb-5 min-w-0 rounded-card border border-border bg-surface p-3 shadow-card max-[767px]:top-0" aria-label="Bộ lọc dashboard">
      <div className="flex items-center justify-between gap-3 md:hidden">
        <Button aria-expanded={expanded} aria-controls={`${id}-fields`} onClick={() => setExpanded(!expanded)}><DashboardIcon name="filter" />Bộ lọc · {value.provinceCode === 'all' ? 'Toàn quốc' : provinces.find((p) => p.provinceCode === value.provinceCode)?.provinceName ?? value.provinceCode}</Button>
        <Button onClick={() => { setCustomRange(false); onReset() }} aria-label="Đặt lại bộ lọc"><DashboardIcon name="reset" /></Button>
      </div>
      <div id={`${id}-fields`} className={`${expanded ? 'grid' : 'hidden'} grid-cols-2 items-end gap-3 max-md:mt-3 md:grid ${variant === 'admin' ? 'md:grid-cols-4 xl:grid-cols-[1.4fr_1.1fr_.7fr_.8fr_1fr_1fr_auto]' : 'md:grid-cols-[1.4fr_1fr_1fr_auto]'}`}>
        <Field>Tỉnh / thành
          <Select aria-label="Tỉnh / thành" disabled={!dataReady} value={value.provinceCode} onChange={(event) => update('provinceCode', event.target.value)}>
            <option value="all">Toàn quốc</option>
            {provinces.map((province) => <option key={province.provinceCode} value={province.provinceCode}>{province.provinceName}</option>)}
          </Select>
        </Field>
        <Field>Chỉ số
          <Select aria-label="Chỉ số" disabled={!pollutantOptions.length} value={value.pollutant} onChange={(event) => update('pollutant', event.target.value as Pollutant)}>
            {!pollutantOptions.length && <option value={value.pollutant}>Chưa có dữ liệu</option>}
            {pollutantOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </Select>
        </Field>
        {variant === 'user' ? <Field>Khoảng thời gian
          <Select aria-label="Khoảng thời gian" value={period} onChange={(event) => {
            const next = event.target.value
            setCustomRange(next === 'custom')
            onChange({ ...value, year: next === 'current' || next === 'custom' ? 'all' : Number(next), month: 'all', startDate: '', endDate: '' })
          }}>
            <option value="current">Bản ghi mới nhất</option>
            {years.map((year) => <option key={year} value={year}>Năm {year}</option>)}
            <option value="custom">Khoảng ngày tùy chọn</option>
          </Select>
        </Field> : <>
          <Field>Năm<Select aria-label="Năm" value={value.year} onChange={(event) => update('year', event.target.value === 'all' ? 'all' : Number(event.target.value))}><option value="all">Tất cả</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</Select></Field>
          <Field>Tháng<Select aria-label="Tháng" value={value.month} onChange={(event) => update('month', event.target.value === 'all' ? 'all' : Number(event.target.value))}><option value="all">Tất cả</option>{Array.from({ length: 12 }, (_, i) => <option key={i} value={i + 1}>Tháng {i + 1}</option>)}</Select></Field>
        </>}
        {(variant === 'admin' || period === 'custom') && <>
          <Field>Từ ngày<DateInput aria-label="Từ ngày" value={value.startDate} max={value.endDate || undefined} onChange={(event) => update('startDate', event.target.value)} /></Field>
          <Field>Đến ngày<DateInput aria-label="Đến ngày" value={value.endDate} min={value.startDate || undefined} onChange={(event) => update('endDate', event.target.value)} /></Field>
        </>}
        <Button className="h-10 max-md:hidden" onClick={() => { setCustomRange(false); onReset() }}><DashboardIcon name="reset" size="small" />Đặt lại</Button>
        {variant === 'admin' && sectors.length > 0 && <Field className="md:col-span-2 xl:col-span-2">Ngành phát thải<Select aria-label="Ngành phát thải" disabled={!dataReady} value={value.sector} onChange={(event) => update('sector', event.target.value)}><option value="all">Tất cả ngành</option>{sectors.map((sector) => <option key={sector} value={sector}>{sector}</option>)}</Select></Field>}
      </div>
    </section>
  )
}
