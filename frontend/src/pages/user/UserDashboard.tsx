import { SourceDetails } from '../../features/dashboard/components/SourceDetails'
import { useCallback, useMemo, useState } from 'react'
import { DashboardBreadcrumb } from '../../features/dashboard/components/DashboardBreadcrumb'
import { DashboardFilters } from '../../features/dashboard/components/DashboardFilters'
import { DashboardIcon } from '../../components/ui/DashboardIcon'
import { ConcentrationSummary } from '../../features/dashboard/components/ConcentrationSummary'
import { AQISummaryCard } from '../../features/dashboard/components/AQISummaryCard'
import { PollutantMetrics } from '../../features/dashboard/components/PollutantMetrics'
import { ObservationTable } from '../../features/dashboard/components/ObservationTable'
import { DashboardComparison } from '../../features/dashboard/components/DashboardComparison'
import { Button } from '../../components/ui/Button'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap } from '../../features/geography/VietnamProvinceMap'
import { useDashboardData } from '../../features/dashboard/hooks/useDashboardData'
import { basicPollutants, buildMonitoringView, DEFAULT_FILTERS, metricOptions, periodLabel } from '../../features/dashboard/model/dashboardSelectors'
import { periodDefaults, periodYears, temporalQuery, trendDescription } from '../../features/dashboard/model/temporal'
import { loadDashboardData } from '../../features/dashboard/api/dashboardApi'
import { expandTrendPeriod, mergeFilterSelection } from '../../features/dashboard/model/filterPeriods'
import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../features/dashboard/types'

export default function UserDashboard() {
  const [selection, setFilters] = useState<Partial<DashboardFiltersValue>>({})
  const query = temporalQuery(selection)
  const { data, loading, error, retry } = useDashboardData(query)
  const dataReady = Boolean(data) && !loading && !error
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const options = useMemo(() => metricOptions(data, true), [data])
  const pollutants = useMemo(() => basicPollutants(data), [data])
  const selectedPollutant = selection.pollutant ?? DEFAULT_FILTERS.pollutant
  const pollutant = options.some((option) => option.value === selectedPollutant) ? selectedPollutant : options[0]?.value ?? 'pm25'
  const resolution = selection.resolution ?? DEFAULT_FILTERS.resolution
  const filters = useMemo(() => {
    const defaults = periodDefaults(data?.metadata, resolution)
    return { ...DEFAULT_FILTERS, ...selection, pollutant, resolution,
      startDate: selection.startDate || defaults.startDate, endDate: selection.endDate || defaults.endDate }
  }, [data, selection, pollutant, resolution])
  const view = useMemo(() => buildMonitoringView(dataReady ? data : null, filters, false), [data, dataReady, filters])
  const years = useMemo(() => periodYears(data?.metadata, [...new Set(data?.dashboardTrendRecords.map((record) => Number(record.date.slice(0, 4))) ?? [])].sort((a, b) => b - a), resolution), [data, resolution])
  const selectFilters = useCallback((next: DashboardFiltersValue) => setFilters((value) => mergeFilterSelection(value, next, filters)), [filters])
  const selectProvince = useCallback((province: ProvinceSnapshot) => setFilters((value) => ({ ...value, provinceCode: province.provinceCode })), [])
  const selectPollutant = useCallback((next: Pollutant) => setFilters((value) => ({ ...value, pollutant: next })), [])
  const period = periodLabel(filters, data?.metadata?.timezone)
  const expandedPeriod = view.chartPoints.length === 1 ? expandTrendPeriod(filters, view.chartPoints[0].timestamp, data?.metadata) : null

  return <main className="mx-auto w-full max-w-[1800px] px-8 pt-6 pb-8 wrap-anywhere max-md:px-4 max-md:pt-4">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="rounded-2xl bg-accent p-3 text-surface shadow-control"><DashboardIcon name="air" /></span>
        <div><p className="text-[.7rem] font-semibold tracking-wider text-accent">CHẤT LƯỢNG KHÔNG KHÍ · VIỆT NAM</p><h1 className="mt-1 text-xl font-semibold tracking-tight text-heading">Chất lượng không khí</h1></div>
      </div>
      <SourceDetails metadata={data?.metadata} metric={pollutant} />
    </header>

    <DashboardBreadcrumb items={[{ id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((value) => ({ ...value, provinceCode: 'all' })) }, ...(filters.provinceCode === 'all' ? [] : [{ id: 'province', label: view.scopeLabel }])]} />
    {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft p-4 text-sm text-danger"><p>{error}</p><Button onClick={retry}>Thử lại</Button></div>}
    {loading && <p role="status" className="mb-3 text-xs text-muted">Đang tải số liệu. Bản đồ vẫn có thể sử dụng.</p>}
    <DashboardFilters variant="user" value={filters} years={years} pollutantOptions={options} dataReady={dataReady} loading={loading} metadata={data?.metadata} provinces={data?.provinceSnapshots ?? []} onChange={selectFilters} onReset={() => setFilters({})} />
    <div className="grid grid-cols-[minmax(0,2.2fr)_minmax(270px,1fr)] items-start gap-4 max-lg:grid-cols-1">
      <VietnamProvinceMap variant="user" provinceSnapshots={view.snapshots} snapshotDate={null} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={pollutant} periodLabel={period} layerVisible={mapLayerVisible} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={selectProvince} />
      <aside className="grid min-w-0 gap-4 max-lg:grid-cols-2 max-[640px]:grid-cols-1">
        {data?.metadata?.cadenceHours && view.aqi === null ? <ConcentrationSummary label={view.metric.label} unit={view.metric.unit} value={view.metrics[pollutant]} pollutant={pollutant} records={view.records} scope={view.scopeLabel} period={period} loading={loading} /> : <AQISummaryCard calendarTimezone={data?.metadata?.timezone} aqi={view.aqi} scopeLabel={view.scopeLabel} period={period} snapshotDate={null} loading={loading} />}
        <section className="min-w-0" aria-label="Các chất ô nhiễm chính"><h2 className="mb-3 text-sm font-semibold text-heading">Chất ô nhiễm chính</h2><PollutantMetrics metrics={view.metrics} metadata={data?.metadata?.metrics} pollutants={pollutants} selected={pollutant} onSelect={selectPollutant} /></section>

      </aside>
    </div>
    <div className="mt-4"><TrendChart dataReady={dataReady} loading={loading} title={`${view.metric.label} · ${view.scopeLabel}`} description={trendDescription(resolution)} points={view.chartPoints} resolution={resolution} observationContext={view.observationContext} onExpandPeriod={expandedPeriod ? () => selectFilters(expandedPeriod) : undefined} metricLabel={view.metric.label} unit={view.metric.unit} fileName={`xu-huong-${pollutant}-${filters.provinceCode}`} /></div>
    <details className="mt-4 rounded-card border border-border bg-surface p-3"><summary className="cursor-pointer text-sm font-semibold text-heading">So sánh khu vực / lịch sử</summary><DashboardComparison data={dataReady ? data : null} filters={filters} years={years} unit={view.metric.unit} loading={loading} load={loadDashboardData} /></details>
    <details className="mt-4 rounded-card border border-border bg-surface p-3"><summary className="cursor-pointer px-2 py-1 text-sm font-semibold text-heading">Chi tiết quan sát và xuất CSV</summary><ObservationTable key={`${query}-${filters.provinceCode}`} records={view.records} provinces={data?.provinceSnapshots ?? []} provinceCode={filters.provinceCode} pollutant={pollutant} timezone={data?.metadata?.timezone} metricLabel={view.metric.label} unit={view.metric.unit} dataReady={dataReady} loading={loading} /></details>
  </main>
}
