import { useEffect, useId, useRef, useState } from 'react'
import type { DashboardFiltersValue, DashboardMetadata, Pollutant, ProvinceSnapshot } from '../types'
import { DashboardIcon } from '../../../components/ui/DashboardIcon'
import { Button, SegmentedControl } from '../../../components/ui/Button'
import { SearchSelect } from '../../../components/ui/SearchSelect'
import { PeriodPicker } from './PeriodPicker'
import { shiftPeriod, shortPeriod } from '../model/filterPeriods'
import { sectorLabel } from '../model/presentation'

interface DashboardFiltersProps {
  variant?: 'user' | 'admin'
  years: number[]
  pollutantOptions: Array<{ value: Pollutant; label: string }>
  dataReady?: boolean
  loading?: boolean
  metadata?: DashboardMetadata | null
  value: DashboardFiltersValue
  provinces: ProvinceSnapshot[]
  sectors?: string[]
  onChange: (value: DashboardFiltersValue) => void
  onReset: () => void
}

export function DashboardFilters({ variant = 'admin', years, pollutantOptions, dataReady = true, loading = false, metadata, value, provinces, sectors = [], onChange, onReset }: DashboardFiltersProps) {
  const sentinel = useRef<HTMLDivElement>(null)
  const panel = useRef<HTMLElement>(null)
  const controlsId = useId()
  const [stuck, setStuck] = useState(false)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    const observer = new IntersectionObserver(([entry]) => {
      const next = !entry.isIntersecting && entry.boundingClientRect.top < 12
      setStuck(next)
      if (!next) setExpanded(false)
    }, { rootMargin: '-12px 0px 0px 0px', threshold: 0 })
    if (sentinel.current) observer.observe(sentinel.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    const resize = new ResizeObserver(([entry]) => {
      document.documentElement.style.setProperty('--filter-scroll-offset', `${entry.target.getBoundingClientRect().height + 28}px`)
    })
    if (panel.current) resize.observe(panel.current)
    return () => { resize.disconnect(); document.documentElement.style.removeProperty('--filter-scroll-offset') }
  }, [])
  const province = value.provinceCode === 'all' ? 'Toàn quốc' : provinces.find((province) => province.provinceCode === value.provinceCode)?.provinceName ?? 'Khu vực đang chọn'
  const metric = pollutantOptions.find((option) => option.value === value.pollutant)?.label ?? 'Chỉ số đang chọn'
  const previous = shiftPeriod(value, -1, metadata)
  const next = shiftPeriod(value, 1, metadata)
  return <><div ref={sentinel} className="filter-sentinel" aria-hidden="true" />
  <section ref={panel} className="dashboard-filters mb-4 rounded-xl border border-border bg-surface shadow-card" data-filter-container data-stuck={stuck} data-expanded={expanded} aria-label="Bộ lọc dữ liệu">
    <button type="button" className="filter-collapsed-toggle" data-filter-toggle aria-expanded={expanded} aria-controls={controlsId} onClick={() => setExpanded((value) => !value)}>
      <span className="min-w-0"><span className="block truncate text-xs font-semibold text-heading">{province} · {metric}</span><span className="mt-1 block truncate text-[.68rem] text-muted">{shortPeriod(value)}</span></span>
      <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-accent"><DashboardIcon name="filter" size="small" />{expanded ? 'Thu gọn' : 'Bộ lọc'}</span>
    </button>
    <div id={controlsId} className="filter-toolbar-shell">
    <div className="filter-toolbar">
      <div className="filter-resolution hidden min-w-0 items-center gap-2 sm:flex">
        <DashboardIcon name="filter" size="small" className="max-sm:hidden text-accent" />
        <SegmentedControl aria-label="Xem dữ liệu theo" className="min-w-0! shrink!">
          {([{ value: '3h', label: '3 giờ' }, { value: 'daily', label: 'Ngày' }, { value: 'monthly', label: 'Tháng' }] as const).map((option) =>
            <Button variant="segment" key={option.value} aria-pressed={value.resolution === option.value} onClick={() => onChange({ ...value, resolution: option.value, year: 'all', month: 'all', startDate: '', endDate: '' })}>{option.label}</Button>)}
        </SegmentedControl>
      </div>
      <div className="filter-province min-w-0"><SearchSelect label="Khu vực" value={value.provinceCode} disabled={!dataReady && !provinces.length}
        options={[{ value: 'all', label: 'Toàn quốc' }, ...provinces.map((province) => ({ value: province.provinceCode, label: province.provinceName }))]} onChange={(provinceCode) => onChange({ ...value, provinceCode })} /></div>
      <div className="filter-pollutant min-w-0"><SearchSelect label="Chỉ số" value={value.pollutant} disabled={!pollutantOptions.length} options={pollutantOptions} onChange={(pollutant) => onChange({ ...value, pollutant: pollutant as Pollutant })} /></div>
      <div className="filter-period flex min-w-0 items-center gap-1">
        <Button variant="icon" className="filter-period-arrow max-sm:hidden" aria-label="Khoảng thời gian trước" title="Xem khoảng thời gian trước" disabled={!previous || loading} onClick={() => previous && onChange(previous)}><DashboardIcon name="chevronLeft" /></Button>
        <div className="min-w-0 flex-1"><PeriodPicker value={value} years={years} metadata={metadata} onChange={onChange} /></div>
        <Button variant="icon" className="filter-period-arrow max-sm:hidden" aria-label="Khoảng thời gian sau" title="Xem khoảng thời gian sau" disabled={!next || loading} onClick={() => next && onChange(next)}><DashboardIcon name="chevronRight" /></Button>
      </div>
      <div className="filter-actions flex items-center justify-end gap-2">
        <span role="status" aria-live="polite" className="filter-status" aria-label={loading ? 'Đang cập nhật dữ liệu' : 'Bộ lọc đã áp dụng'}><span className={`filter-status-dot ${loading ? 'filter-status-loading' : ''}`} /></span>
        <Button aria-label="Đặt lại bộ lọc" title="Đặt lại bộ lọc" className="min-h-10! min-w-10!" onClick={onReset}><DashboardIcon name="reset" size="small" /></Button>
      </div>
    </div>
    {variant === 'admin' && sectors.length > 0 && <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2"><span className="text-xs text-muted">Ngành phát thải</span><div className="min-w-0 max-w-full sm:w-64"><SearchSelect label="Ngành" value={value.sector} options={[{ value: 'all', label: 'Tất cả các ngành' }, ...sectors.map((sector) => ({ value: sector, label: sectorLabel(sector) }))]} onChange={(sector) => onChange({ ...value, sector })} /></div></div>}
    </div>
  </section></>
}
