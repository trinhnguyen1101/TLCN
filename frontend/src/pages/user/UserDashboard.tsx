import { useState } from 'react'
import { ComparisonPanel, type ComparisonValue } from '../../components/dashboard/ComparisonPanel'
import { DashboardBreadcrumb } from '../../components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from '../../components/dashboard/DashboardFilters'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { DataState } from '../../components/dashboard/DataState'
import { DashboardSkeleton } from '../../components/dashboard/DashboardSkeleton'
import { Skeleton } from '../../components/ui/Skeleton'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap, type MapMetric } from '../../features/geography/VietnamProvinceMap'
import { Button } from '../../components/ui/Button'
import { useDashboardData } from '../../hooks/useDashboardData'
import type { ChartPoint, DashboardData, DashboardFiltersValue, DashboardTrendRecord, Pollutant, ProvinceCode } from '../../types/dashboard'

// An empty collection represents unavailable API data, never a mock fallback.
const EMPTY_DASHBOARD_DATA: DashboardData = {
  provinceSnapshots: [],
  emissionRecords: [],
  emissionSectors: [],
  dashboardTrendRecords: [],
}

const DEFAULT_FILTERS: DashboardFiltersValue = {
  provinceCode: 'all',
  pollutant: 'pm25',
  year: 'all',
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
  pm1: { label: 'PM1', unit: 'µg/m³' },
  aod550: { label: 'AOD 550 nm', unit: '1' },
  o3Column: { label: 'O₃ tổng cột', unit: 'mg/m²' },
  no2Column: { label: 'NO₂ tổng cột', unit: 'mg/m²' },
  so2Column: { label: 'SO₂ tổng cột', unit: 'mg/m²' },
  coColumn: { label: 'CO tổng cột', unit: 'mg/m²' },
  t2m: { label: 'Nhiệt độ 2 m', unit: '°C' },
  d2m: { label: 'Điểm sương 2 m', unit: '°C' },
  sp: { label: 'Áp suất bề mặt', unit: 'hPa' },
  mslp: { label: 'Áp suất mực biển', unit: 'hPa' },
  u10: { label: 'Gió 10 m hướng đông', unit: 'm/s' },
  v10: { label: 'Gió 10 m hướng bắc', unit: 'm/s' },
}

const isNumber = (value: number | null | undefined): value is number => typeof value === 'number' && Number.isFinite(value)

const mean = (values: number[]) => values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null

export default function UserDashboard() {
  const { data, loading, error, retry } = useDashboardData()

  return <Dashboard data={data} loading={loading} error={error} onRetry={retry} />
}

interface DashboardProps {
  data: DashboardData | null
  loading: boolean
  error: string | null
  onRetry: () => void
}

function Dashboard({ data, loading, error, onRetry }: DashboardProps) {
  const dataReady = data !== null
  const { dashboardTrendRecords, emissionRecords, emissionSectors, provinceSnapshots } = data ?? EMPTY_DASHBOARD_DATA
  const years = [...new Set(dashboardTrendRecords.map((record) => Number(record.date.slice(0, 4))))].sort((a, b) => b - a)
  const defaultFilters: DashboardFiltersValue = { ...DEFAULT_FILTERS, year: years[0] ?? 'all' }
  const availableMetrics = (data?.metadata ? Object.keys(data.metadata.metrics) : ['pm25', 'pm10', 'o3', 'no2', 'so2', 'co'])
    .filter((value): value is Pollutant => Object.hasOwn(metricMeta, value))
  const pollutantOptions = availableMetrics.map((value) => ({ value, label: metricMeta[value].label }))
  // Derive defaults as data arrives without remounting the map or resetting user choices.
  const [filterSelection, setFilters] = useState<Partial<DashboardFiltersValue>>({})
  const selectedPollutant = filterSelection.pollutant ?? defaultFilters.pollutant
  const filters: DashboardFiltersValue = {
    ...defaultFilters, ...filterSelection,
    pollutant: availableMetrics.includes(selectedPollutant) ? selectedPollutant : availableMetrics[0] ?? 'pm25',
  }
  const [comparisonSelection, setComparison] = useState<Partial<ComparisonValue>>({})
  const comparison: ComparisonValue = { dimension: 'province', provinceCode: provinceSnapshots[1]?.provinceCode ?? provinceSnapshots[0]?.provinceCode ?? '', year: years[1] ?? years[0] ?? 0, ...comparisonSelection }
  const [mapMetric, setMapMetric] = useState<MapMetric>('pm25')
  const [mapLayerVisible, setMapLayerVisible] = useState(true)

  const recordMatches = (record: DashboardTrendRecord, provinceCode = filters.provinceCode, year = filters.year, alignDatesToYear = false) => {
    if (provinceCode !== 'all' && record.provinceCode !== provinceCode) return false
    if (year !== 'all' && Number(record.date.slice(0, 4)) !== year) return false
    if (filters.month !== 'all' && Number(record.date.slice(5, 7)) !== filters.month) return false
    const dateYear = alignDatesToYear && year !== 'all' ? year : null
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
      const value = record[filters.pollutant]
      if (!isNumber(value)) return
      values.push(value)
      grouped.set(key, values)
    })
    return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, values]) => ({
      label: filters.year === 'all' ? `${date.slice(5)}/${date.slice(2, 4)}` : `T${Number(date.slice(5))}`,
      value: Number((mean(values) ?? 0).toFixed(3)),
    }))
  })()

  const currentYear = filters.year === 'all' ? years[0] : filters.year
  const currentProvince = filters.provinceCode
  const averageFor = (provinceCode: ProvinceCode | 'all', year: number | 'all', alignDatesToYear = false) => mean(
    dashboardTrendRecords
      .filter((record) => recordMatches(record, provinceCode, year, alignDatesToYear))
      .map((record) => record[filters.pollutant]).filter(isNumber),
  )

  const currentComparisonValue = comparison.dimension === 'province'
    ? averageFor(currentProvince, filters.year)
    : averageFor(currentProvince, currentYear)
  const otherComparisonValue = comparison.dimension === 'province'
    ? averageFor(comparison.provinceCode as ProvinceCode, filters.year)
    : averageFor(currentProvince, comparison.year, true)

  const provinceName = (code: string) => provinceSnapshots.find((province) => province.provinceCode === code)?.provinceName ?? 'Toàn quốc'
  const periodPrefix = filters.month === 'all' ? '' : `Tháng ${filters.month} · `
  const currentComparisonLabel = comparison.dimension === 'province'
    ? provinceName(currentProvince)
    : `${periodPrefix}${currentYear}`
  const otherComparisonLabel = comparison.dimension === 'province'
    ? provinceName(comparison.provinceCode)
    : `${periodPrefix}${comparison.year}`

  const filteredEmissions = emissionRecords.filter((record) => {
    if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
    if (filters.year !== 'all' && record.year !== filters.year) return false
    if (filters.month !== 'all' && record.month !== filters.month) return false
    if (filters.sector !== 'all' && record.sector !== filters.sector) return false
    const month = `${record.year}-${String(record.month).padStart(2, '0')}`
    if (filters.startDate && month < filters.startDate.slice(0, 7)) return false
    if (filters.endDate && month > filters.endDate.slice(0, 7)) return false
    return true
  })
  const totalEmissions = filteredEmissions.reduce((sum, record) => sum + record.emissionTonnes, 0)

  const breadcrumbItems = [
    { id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((current) => ({ ...current, provinceCode: 'all' })) },
    ...(filters.provinceCode !== 'all' ? [{ id: 'province', label: provinceName(filters.provinceCode), onSelect: filters.year === 'all' ? undefined : () => setFilters((current) => ({ ...current, year: 'all', month: 'all' })) }] : []),
    ...(filters.year !== 'all' ? [{ id: 'year', label: String(filters.year), onSelect: filters.month === 'all' ? undefined : () => setFilters((current) => ({ ...current, month: 'all' })) }] : []),
    ...(filters.month !== 'all' ? [{ id: 'month', label: `Tháng ${filters.month}` }] : []),
  ]

  const metric = { ...metricMeta[filters.pollutant], ...data?.metadata?.metrics[filters.pollutant] }
  const scopeLabel = filters.provinceCode === 'all' ? 'Toàn quốc' : provinceName(filters.provinceCode)
  const periodLabel = [filters.month === 'all' ? null : `Tháng ${filters.month}`, filters.year === 'all' ? 'Tất cả các năm' : `Năm ${filters.year}`].filter(Boolean).join(' · ')
  const averageConcentration = mean(filteredRecords.map((record) => record[filters.pollutant]).filter(isNumber))

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
      {data?.metadata && <p className="mb-6 text-[.83rem] text-muted">{data.metadata.note} Bản đồ: {data.metadata.snapshotDate?.slice(0, 7) ?? 'chưa có dữ liệu'} (UTC).</p>}

      {error && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft px-5 py-4 text-[.83rem] text-danger" role="alert">
          <p className="flex-1 basis-64">{error}</p>
          <Button onClick={onRetry}>Thử lại</Button>
        </div>
      )}
      {loading && <p className="mb-6 text-[.83rem] text-muted" role="status">Đang tải số liệu. Bạn vẫn có thể xem bản đồ.</p>}

      <section className="mb-6 grid grid-cols-3 gap-5 max-[680px]:grid-cols-1 max-[680px]:gap-3" aria-label="Tóm tắt bộ lọc" aria-busy={loading}>
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-border bg-surface">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>Khu vực theo dõi</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-accent-soft text-accent"><DashboardIcon name="location" /></span></div>
          <strong className="mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] min-h-[45px] items-center text-[1.6rem] tracking-[-.025em] text-heading">{scopeLabel}</strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{!dataReady ? <><Skeleton animated={loading} className="h-3.5 w-40" /><span className="sr-only">{loading ? 'Đang tải số tỉnh, thành có dữ liệu…' : 'Chưa tải được số tỉnh, thành có dữ liệu.'}</span></> : filters.provinceCode === 'all' ? `${provinceSnapshots.filter((province) => province.pm25 !== null || province.pm10 !== null).length} tỉnh, thành có dữ liệu PM` : 'Việt Nam'}</p>
        </article>
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-accent-border bg-[#102c2c]">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>{metric.label} trung bình</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-[#1c4841] text-accent"><DashboardIcon name="chart" /></span></div>
          <strong className={`mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] text-accent-hover ${averageConcentration === null ? 'min-h-[45px] items-center text-[1.2rem] tracking-[-.02em]' : 'items-baseline text-[2.15rem] tracking-[-.04em]'}`}>
            {!dataReady ? <><Skeleton animated={loading} className="h-9 w-32" /><span className="sr-only">{loading ? 'Đang tải số liệu…' : 'Chưa tải được số liệu.'}</span></> : averageConcentration?.toFixed(metric.unit === '1' ? 3 : 1) ?? 'Chưa có dữ liệu'}
            {averageConcentration !== null && <span className="text-[.9rem] font-normal tracking-normal text-muted">{metric.unit}</span>}
          </strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{periodLabel}</p>
        </article>
        <article className="flex min-w-0 flex-col items-start rounded-card border px-6 py-5 shadow-card max-[1100px]:p-[18px] max-[680px]:px-5 border-border bg-surface">
          <div className="flex w-full items-center justify-between gap-3 text-[.82rem] font-medium text-secondary"><span>Tổng phát thải</span><span className="grid size-[34px] shrink-0 place-items-center rounded-[9px] bg-[#1c304c] text-[#a5c9ff]"><DashboardIcon name="emission" /></span></div>
          <strong className={`mt-2.5 flex flex-wrap gap-2 font-[650] leading-[1.3] tabular-nums wrap-anywhere max-[680px]:mt-[5px] text-heading ${filteredEmissions.length ? 'items-baseline text-[2.15rem] tracking-[-.04em]' : 'min-h-[45px] items-center text-[1.2rem] tracking-[-.02em]'}`}>
            {!dataReady ? <><Skeleton animated={loading} className="h-9 w-32" /><span className="sr-only">{loading ? 'Đang tải số liệu…' : 'Chưa tải được số liệu.'}</span></> : filteredEmissions.length ? totalEmissions.toLocaleString('vi-VN') : 'Chưa có dữ liệu'}
            {filteredEmissions.length > 0 && <span className="text-[.9rem] font-normal tracking-normal text-muted">tấn</span>}
          </strong>
          <p className="mt-[7px] text-[.77rem] leading-normal text-muted">{filters.sector === 'all' ? 'Tất cả ngành phát thải' : filters.sector}</p>
        </article>
      </section>

      <DashboardFilters years={years} pollutantOptions={pollutantOptions} dataReady={dataReady} value={filters} provinces={provinceSnapshots} sectors={emissionSectors} onChange={setFilters} onReset={() => setFilters({})} />

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-stretch gap-6 max-[1100px]:grid-cols-1 max-[680px]:mt-4 max-[680px]:gap-4">
        <VietnamProvinceMap
          metricMetadata={data?.metadata?.metrics}
          provinceSnapshots={provinceSnapshots}
          selectedProvinceCode={filters.provinceCode}
          metric={mapMetric}
          layerVisible={mapLayerVisible}
          onMetricChange={setMapMetric}
          onLayerVisibilityChange={setMapLayerVisible}
          onProvinceSelect={(province) => setFilters((current) => ({ ...current, provinceCode: province.provinceCode }))}
        />

        <TrendChart
          dataReady={dataReady}
          loading={loading}
          title={`${metric.label} · ${scopeLabel}`}
          description="Giá trị trung bình theo tháng trong phạm vi đang chọn."
          points={chartPoints}
          metricLabel={metric.label}
          unit={metric.unit}
          fileName={`xu-huong-${filters.pollutant}-${filters.provinceCode}`}
        />

        <ComparisonPanel
          years={years}
          dataReady={dataReady}
          loading={loading}
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
          {!dataReady ? <DashboardSkeleton variant="table" loading={loading} /> : (
            <DataState compact isEmpty={filteredEmissions.length === 0} emptyMessage="Không có số liệu phát thải trong phạm vi đang chọn.">
              <div className="max-h-[350px] overflow-auto focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" role="region" aria-label="Chi tiết phát thải" tabIndex={0}>
                <table className="w-full border-separate border-spacing-0 text-left text-[.83rem]">
                  <thead><tr><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Tỉnh / thành</th><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Ngành phát thải</th><th scope="col" className="sticky top-0 z-1 border-y border-border bg-surface-subtle px-6 py-3 text-[.76rem] font-medium whitespace-nowrap text-muted last:text-right last:tabular-nums max-[680px]:px-5">Lượng phát thải (tấn)</th></tr></thead>
                  <tbody>
                    {filteredEmissions.map((record) => (
                      <tr key={`${record.provinceCode}-${record.year}-${record.month}-${record.sector}`} className="group hover:bg-surface-subtle">
                        <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5">{record.provinceName}</td>
                        <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5"><span className="inline-block rounded-[5px] bg-surface-subtle px-2 py-1 text-[.75rem] text-secondary">{record.sector}</span></td>
                        <td className="border-b border-border px-6 py-[13px] text-secondary first:font-medium first:text-ink last:text-right last:font-semibold last:text-ink last:tabular-nums group-last:border-b-0 max-[680px]:px-5">{record.emissionTonnes.toLocaleString('vi-VN')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DataState>
          )}
        </section>
      </div>
    </main>
  )
}



