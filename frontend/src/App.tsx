import { useMemo, useState } from 'react'
import { ComparisonPanel, type ComparisonValue } from './components/dashboard/ComparisonPanel'
import { DashboardBreadcrumb } from './components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from './components/dashboard/DashboardFilters'
import { DashboardIcon } from './components/dashboard/DashboardIcon'
import { DataState } from './components/dashboard/DataState'
import { TrendChart } from './features/analytics/TrendChart'
import { VietnamProvinceMap, type MapMetric } from './features/geography/VietnamProvinceMap'
import { dashboardTrendRecords, emissionRecords, emissionSectors, provinceSnapshots } from './services/mockDashboardData'
import type { ChartPoint, DashboardFiltersValue, DashboardTrendRecord, ProvinceCode } from './types/dashboard'

const DEFAULT_FILTERS: DashboardFiltersValue = {
  provinceCode: 'all',
  pollutant: 'pm25',
  year: 2026,
  month: 'all',
  startDate: '',
  endDate: '',
  sector: 'all',
}

const metricMeta = {
  pm25: { label: 'PM2.5', unit: 'µg/m³' },
  pm10: { label: 'PM10', unit: 'µg/m³' },
  o3: { label: 'O₃', unit: 'µg/m³' },
  no2: { label: 'NO₂', unit: 'µg/m³' },
  so2: { label: 'SO₂', unit: 'µg/m³' },
  co: { label: 'CO', unit: 'mg/m³' },
}

const mean = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null

function App() {
  const [filters, setFilters] = useState<DashboardFiltersValue>(DEFAULT_FILTERS)
  const [comparison, setComparison] = useState<ComparisonValue>({ dimension: 'province', provinceCode: '24', year: 2025 })
  const [mapMetric, setMapMetric] = useState<MapMetric>('aqi')
  const [mapLayerVisible, setMapLayerVisible] = useState(true)

  const recordMatches = (record: DashboardTrendRecord, provinceCode = filters.provinceCode, year = filters.year) => {
    if (provinceCode !== 'all' && record.provinceCode !== provinceCode) return false
    if (year !== 'all' && Number(record.date.slice(0, 4)) !== year) return false
    if (filters.month !== 'all' && Number(record.date.slice(5, 7)) !== filters.month) return false
    const dateYear = year === 'all' ? null : year
    const startDate = filters.startDate && dateYear ? `${dateYear}${filters.startDate.slice(4)}` : filters.startDate
    const endDate = filters.endDate && dateYear ? `${dateYear}${filters.endDate.slice(4)}` : filters.endDate
    if (startDate && record.date < startDate) return false
    if (endDate && record.date > endDate) return false
    return true
  }

  const filteredRecords = dashboardTrendRecords.filter((record) => recordMatches(record))

  const chartPoints: ChartPoint[] = (() => {
    const grouped = new Map<string, number[]>()
    filteredRecords.forEach((record) => {
      const key = record.date.slice(0, 7)
      const values = grouped.get(key) ?? []
      values.push(record[filters.pollutant])
      grouped.set(key, values)
    })
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, values]) => ({
      label: filters.year === 'all' ? `${date.slice(5)}/${date.slice(2, 4)}` : `T${Number(date.slice(5))}`,
      value: Number((mean(values) ?? 0).toFixed(1)),
    }))
  })()

  const currentYear = filters.year === 'all' ? 2026 : filters.year
  const currentProvince = filters.provinceCode
  const averageFor = (provinceCode: ProvinceCode | 'all', year: number | 'all') => mean(
    dashboardTrendRecords
      .filter((record) => recordMatches(record, provinceCode, year))
      .map((record) => record[filters.pollutant]),
  )

  const currentComparisonValue = comparison.dimension === 'province'
    ? averageFor(currentProvince, filters.year)
    : averageFor(currentProvince, currentYear)
  const otherComparisonValue = comparison.dimension === 'province'
    ? averageFor(comparison.provinceCode as ProvinceCode, filters.year)
    : averageFor(currentProvince, comparison.year)

  const provinceName = (code: string) => provinceSnapshots.find((province) => province.provinceCode === code)?.provinceName ?? 'Toàn quốc'
  const periodPrefix = filters.month === 'all' ? '' : `Tháng ${filters.month} · `
  const currentComparisonLabel = comparison.dimension === 'province'
    ? provinceName(currentProvince)
    : `${periodPrefix}${currentYear}`
  const otherComparisonLabel = comparison.dimension === 'province'
    ? provinceName(comparison.provinceCode)
    : `${periodPrefix}${comparison.year}`

  const filteredEmissions = useMemo(() => emissionRecords.filter((record) => {
    if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
    if (filters.year !== 'all' && record.year !== filters.year) return false
    if (filters.month !== 'all' && record.month !== filters.month) return false
    if (filters.sector !== 'all' && record.sector !== filters.sector) return false
    return true
  }), [filters])
  const totalEmissions = filteredEmissions.reduce((sum, record) => sum + record.emissionTonnes, 0)

  const breadcrumbItems = [
    { id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((current) => ({ ...current, provinceCode: 'all' })) },
    ...(filters.provinceCode !== 'all' ? [{ id: 'province', label: provinceName(filters.provinceCode), onSelect: filters.year === 'all' ? undefined : () => setFilters((current) => ({ ...current, year: 'all', month: 'all' })) }] : []),
    ...(filters.year !== 'all' ? [{ id: 'year', label: String(filters.year), onSelect: filters.month === 'all' ? undefined : () => setFilters((current) => ({ ...current, month: 'all' })) }] : []),
    ...(filters.month !== 'all' ? [{ id: 'month', label: `Tháng ${filters.month}` }] : []),
  ]

  const metric = metricMeta[filters.pollutant]
  const scopeLabel = filters.provinceCode === 'all' ? 'Toàn quốc' : provinceName(filters.provinceCode)
  const periodLabel = [filters.month === 'all' ? null : `Tháng ${filters.month}`, filters.year === 'all' ? 'Tất cả các năm' : `Năm ${filters.year}`].filter(Boolean).join(' · ')
  const averageConcentration = mean(filteredRecords.map((record) => record[filters.pollutant]))

  return (
    <main className="mx-auto w-full max-w-[1440px] px-12 pt-9 pb-14 max-[1100px]:px-7 max-[1100px]:pt-7 max-[1100px]:pb-10 max-[680px]:px-4 max-[680px]:pt-6 max-[680px]:pb-8">
      <header className="flex items-center justify-between gap-6 max-[680px]:flex-col max-[680px]:items-start max-[680px]:gap-4">
        <div className="flex min-w-0 items-center gap-4 max-[680px]:gap-3">
          <span className="grid size-12 shrink-0 place-items-center rounded-[13px] border border-accent-border bg-accent-soft text-accent max-[680px]:size-[42px]"><DashboardIcon name="air" size="brand" /></span>
          <div>
            <p className="mb-[3px] text-[.75rem] font-semibold tracking-[.06em] text-muted">Air Quality</p>
            <h1 className="text-[clamp(1.4rem,2.6vw,1.85rem)] font-[650] tracking-[-.035em] text-heading leading-[1.3]">Chất lượng không khí</h1>
          </div>
        </div>
        <div className="inline-flex shrink-0 items-center gap-[9px] rounded-[9px] border border-border bg-surface px-[13px] py-2.5 text-[.8rem] font-medium text-secondary max-[680px]:px-[11px] max-[680px]:py-2"><DashboardIcon name="calendar" className="text-muted" /><span>{periodLabel}</span></div>
      </header>

      <DashboardBreadcrumb items={breadcrumbItems} />

      <section className="mb-6 grid grid-cols-3 gap-5 max-[680px]:grid-cols-1 max-[680px]:gap-3" aria-label="Tóm tắt bộ lọc">
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-border bg-surface">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>Khu vực theo dõi</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-accent-soft text-accent"><DashboardIcon name="location" /></span></div>
          <strong className="mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] min-h-[45px] items-center text-[1.6rem] tracking-[-.025em] text-heading">{scopeLabel}</strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{filters.provinceCode === 'all' ? `${provinceSnapshots.length} tỉnh, thành có dữ liệu` : 'Việt Nam'}</p>
        </article>
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-accent-border bg-[#102c2c]">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>{metric.label} trung bình</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-[#1c4841] text-accent"><DashboardIcon name="chart" /></span></div>
          <strong className={`mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] text-accent-hover ${averageConcentration === null ? 'min-h-[45px] items-center text-[1.2rem] tracking-[-.02em]' : 'items-baseline text-[2.15rem] tracking-[-.04em]'}`}>
            {averageConcentration?.toFixed(1) ?? 'Chưa có dữ liệu'}
            {averageConcentration !== null && <span className="text-[.9rem] font-normal tracking-normal text-muted">{metric.unit}</span>}
          </strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{periodLabel}</p>
        </article>
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-border bg-surface">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>Tổng phát thải</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-[#1c304c] text-[#a5c9ff]"><DashboardIcon name="emission" /></span></div>
          <strong className={`mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] text-heading ${filteredEmissions.length ? 'items-baseline text-[2.15rem] tracking-[-.04em]' : 'min-h-[45px] items-center text-[1.2rem] tracking-[-.02em]'}`}>
            {filteredEmissions.length ? totalEmissions.toLocaleString('vi-VN') : 'Chưa có dữ liệu'}
            {filteredEmissions.length > 0 && <span className="text-[.9rem] font-normal tracking-normal text-muted">tấn</span>}
          </strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{filters.sector === 'all' ? 'Tất cả ngành phát thải' : filters.sector}</p>
        </article>
      </section>

      <DashboardFilters value={filters} provinces={provinceSnapshots} sectors={emissionSectors} onChange={setFilters} onReset={() => setFilters(DEFAULT_FILTERS)} />

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-stretch gap-6 max-[1100px]:grid-cols-1 max-[680px]:mt-4 max-[680px]:gap-4">
        <VietnamProvinceMap
          selectedProvinceCode={filters.provinceCode}
          metric={mapMetric}
          layerVisible={mapLayerVisible}
          onMetricChange={setMapMetric}
          onLayerVisibilityChange={setMapLayerVisible}
          onProvinceSelect={(province) => setFilters((current) => ({ ...current, provinceCode: province.provinceCode }))}
        />

        <TrendChart
          title={`${metric.label} · ${scopeLabel}`}
          description="Nồng độ trung bình theo tháng trong phạm vi đang chọn."
          points={chartPoints}
          metricLabel={metric.label}
          unit={metric.unit}
          fileName={`xu-huong-${filters.pollutant}-${filters.provinceCode}`}
        />

        <ComparisonPanel
          value={comparison}
          provinces={provinceSnapshots}
          currentLabel={currentComparisonLabel}
          comparisonLabel={otherComparisonLabel}
          currentValue={currentComparisonValue}
          comparisonValue={otherComparisonValue}
          unit={metric.unit}
          onChange={setComparison}
        />

        <section className="col-span-full min-w-0 overflow-hidden rounded-card border border-border bg-surface shadow-card" aria-labelledby="emission-title">
          <div className="flex items-center justify-between gap-4 px-6 py-[22px] max-[680px]:p-5">
            <div>
              <h2 id="emission-title" className="text-[.98rem] font-semibold text-heading">Phát thải theo ngành</h2>
              <p className="mt-1.5 text-[.8rem] text-muted">{scopeLabel}</p>
            </div>
            <span className="shrink-0 text-[.76rem] text-muted">Đơn vị: tấn</span>
          </div>
          <DataState compact isEmpty={filteredEmissions.length === 0} emptyMessage="Không có số liệu phát thải trong phạm vi đang chọn.">
            <div className="max-h-[350px] overflow-auto focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" role="region" aria-label="Chi tiết phát thải" tabIndex={0}>
              <table className="w-full border-separate border-spacing-0 text-left text-[.83rem]">
                <thead><tr><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Tỉnh / thành</th><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Ngành phát thải</th><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Lượng phát thải (tấn)</th></tr></thead>
                <tbody>
                  {filteredEmissions.map((record) => (
                    <tr key={`${record.provinceCode}-${record.sector}`} className="group hover:bg-surface-subtle">
                      <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5">{record.provinceName}</td>
                      <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5"><span className="inline-block rounded-[5px] bg-surface-subtle px-2 py-1 text-[.75rem] text-secondary">{record.sector}</span></td>
                      <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5">{record.emissionTonnes.toLocaleString('vi-VN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DataState>
        </section>
      </div>
    </main>
  )
}

export default App
