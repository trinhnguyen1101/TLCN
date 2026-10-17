import { useCallback, useMemo, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { DashboardBreadcrumb } from '../../features/dashboard/components/DashboardBreadcrumb'
import { DashboardFilters } from '../../features/dashboard/components/DashboardFilters'
import { KpiCard } from '../../features/dashboard/components/KpiCard'
import { ObservationTable } from '../../features/dashboard/components/ObservationTable'
import { HorizontalBarChart } from '../../features/analytics/HorizontalBarChart'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap } from '../../features/geography/VietnamProvinceMap'
import { aqiLevel } from '../../features/geography/mapColorScale'
import { useAdminDashboardData } from '../../features/dashboard/hooks/useAdminDashboardData'
import { buildAdminDashboardView } from '../../features/dashboard/model/adminDashboardModel'
import { DEFAULT_FILTERS, metricOptions, periodLabel } from '../../features/dashboard/model/dashboardSelectors'
import { periodDefaults, periodYears, temporalQuery, trendDescription } from '../../features/dashboard/model/temporal'
import { expandTrendPeriod, mergeFilterSelection } from '../../features/dashboard/model/filterPeriods'
import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../features/dashboard/types'
import { formatDecimal } from '../../utils/formatters'
import { sourceLabel } from '../../features/dashboard/model/presentation'
import { AdminAnalytics } from './AdminAnalytics'

export function AdminDashboard() {
  const [selection, setFilters] = useState<Partial<DashboardFiltersValue>>({})
  const query = temporalQuery(selection)
  const { data, loading, error, retry, comparisonLoading, comparisonError } = useAdminDashboardData(query)
  const dataReady = Boolean(data) && !loading && !error
  const visibleData = dataReady ? data : null
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const [tab, setTab] = useState('overview')
  const scope = useMemo(() => {
    const resolution = selection.resolution ?? DEFAULT_FILTERS.resolution
    const defaults = periodDefaults(data?.metadata, resolution)
    return { ...DEFAULT_FILTERS, ...selection, resolution,
      startDate: selection.startDate || defaults.startDate, endDate: selection.endDate || defaults.endDate }
  }, [data, selection])
  const options = useMemo(() => metricOptions(data), [data])
  const pollutant = options.some((option) => option.value === scope.pollutant) ? scope.pollutant : options[0]?.value ?? 'pm25'
  const filters = useMemo(() => ({ ...scope, pollutant }), [scope, pollutant])
  const view = useMemo(() => buildAdminDashboardView(visibleData, filters), [visibleData, filters])
  const years = useMemo(() => periodYears(data?.metadata, [...new Set(data?.dashboardTrendRecords.map((record) => Number(record.date.slice(0, 4))) ?? [])].sort((a, b) => b - a), scope.resolution), [data, scope.resolution])
  const { monitoring, metric, scopeLabel, selectedPollutant } = view
  const selectFilters = useCallback((next: DashboardFiltersValue) => setFilters((value) => mergeFilterSelection(value, next, filters)), [filters])
  const selectProvinceCode = useCallback((provinceCode: string) => setFilters((current) => ({ ...current, provinceCode })), [])
  const selectProvince = useCallback((province: ProvinceSnapshot) => selectProvinceCode(province.provinceCode), [selectProvinceCode])
  const selectPollutant = useCallback((pollutant: Pollutant) => setFilters((current) => ({ ...current, pollutant })), [])
  const selectSector = useCallback((sector: string) => setFilters((current) => ({ ...current, sector: current.sector === sector ? 'all' : sector })), [])
  const period = periodLabel(filters)
  const expandedPeriod = view.chartPoints.length === 1 ? expandTrendPeriod(filters, view.chartPoints[0].timestamp, data?.metadata) : null
  const aqi = aqiLevel(view.currentAqi)

  return <main className="mx-auto w-full max-w-[1800px] px-8 pt-6 pb-8 wrap-anywhere max-md:px-4 max-md:pt-4">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-[.7rem] font-semibold tracking-wider text-accent">CHẤT LƯỢNG KHÔNG KHÍ · QUẢN LÝ</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-heading">Tổng quan điều hành</h1></div>
      <span className="rounded-full border border-accent-border bg-accent-soft px-3 py-1.5 text-xs text-accent">{sourceLabel(data?.metadata?.source) ?? 'Giám sát & phân tích'}</span>
    </header>
    <DashboardBreadcrumb items={[{ id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => selectProvinceCode('all') }, ...(filters.provinceCode === 'all' ? [] : [{ id: 'province', label: scopeLabel }]), { id: 'period', label: period }]} />
    {error && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft p-4 text-sm text-danger" role="alert"><span>{error}</span><Button onClick={retry}>Thử lại</Button></div>}
    {loading && <p role="status" className="mb-3 text-xs text-muted">Đang tải dữ liệu quản lý…</p>}
    <DashboardFilters variant="admin" value={filters} years={years} pollutantOptions={options} dataReady={dataReady} loading={loading} metadata={data?.metadata} provinces={data?.provinceSnapshots ?? []} sectors={data?.emissionSectors ?? []} onChange={selectFilters} onReset={() => setFilters({})} />
    {comparisonError && <div role="alert" className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-danger"><span>Đã tải dữ liệu đang xem. Chưa tải được dữ liệu so sánh: {comparisonError}</span><Button onClick={retry}>Thử lại</Button></div>}
    <section className="mb-4 grid grid-cols-5 gap-3 max-[1199px]:grid-cols-3 max-md:grid-cols-2" aria-label="Các chỉ số tổng quan" aria-busy={loading}>
      <KpiCard icon="chart" label={`${metric.label} trung bình`} value={formatDecimal(monitoring.metrics[selectedPollutant], metric.unit)} detail={scopeLabel} tone="yellow" loading={loading} />
      <KpiCard icon="air" label="AQI trung bình" value={formatDecimal(view.currentAqi)} detail={aqi?.label ?? 'Nguồn chưa cung cấp AQI'} valueColor={aqi?.textColor} loading={loading} />
      <KpiCard icon="location" label={`Tỉnh có ${metric.label} cao nhất`} value={monitoring.ranking[0]?.label ?? 'Chưa có dữ liệu'} detail={monitoring.ranking[0] ? formatDecimal(monitoring.ranking[0].value, metric.unit) : period} loading={loading} />
      <KpiCard icon="layers" label={`Tỉnh có dữ liệu ${metric.label}`} value={dataReady ? `${monitoring.reportingProvinces}` : 'Chưa có dữ liệu'} detail="Trong phạm vi bộ lọc" loading={loading} />
      <KpiCard icon="chart" label={`Thay đổi ${metric.label} cùng kỳ`} value={view.yoy === null ? 'Chưa có dữ liệu' : `${view.yoy > 0 ? '+' : ''}${view.yoy.toFixed(1)}%`} detail={comparisonLoading ? 'Đang tải dữ liệu so sánh…' : view.currentYear === undefined ? 'Chọn khoảng thời gian để so sánh' : `So với cùng thời gian năm ${view.currentYear - 1}`} trend={view.yoy === null ? 'neutral' : view.yoy > 0 ? 'up' : 'down'} loading={loading || comparisonLoading} />
    </section>
    <section className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-stretch gap-4 max-lg:grid-cols-1" aria-label="Giám sát không gian và thời gian">
      <VietnamProvinceMap variant="admin" provinceSnapshots={monitoring.snapshots} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={selectedPollutant} periodLabel={period} layerVisible={mapLayerVisible} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={selectProvince} />
      <div className="grid min-w-0 content-start gap-4 max-lg:grid-cols-2 max-md:grid-cols-1">
        <TrendChart compact dataReady={dataReady} loading={loading} title={`${metric.label} · ${scopeLabel}`} description={trendDescription(filters.resolution)} points={view.chartPoints} resolution={filters.resolution} observationContext={monitoring.observationContext} onExpandPeriod={expandedPeriod ? () => selectFilters(expandedPeriod) : undefined} metricLabel={metric.label} unit={metric.unit} fileName={`xu-huong-${selectedPollutant}-${filters.provinceCode}`} />
        <HorizontalBarChart compact dataReady={dataReady} loading={loading} eyebrow="So sánh khu vực" title={`Các tỉnh có ${metric.label} cao nhất`} description="Giá trị trung bình trong khoảng thời gian đã chọn. Bấm vào một thanh để xem dữ liệu của tỉnh đó." points={monitoring.ranking.slice(0, 5)} unit={metric.unit} fileName={`xep-hang-tinh-${selectedPollutant}`} selectedId={filters.provinceCode} onSelect={(point) => selectProvinceCode(point.id)} />
      </div>
    </section>
    <AdminAnalytics data={visibleData} filters={filters} view={view} loading={loading} tab={tab} onTabChange={setTab} onProvinceSelect={selectProvinceCode} onPollutantSelect={selectPollutant} onSectorSelect={selectSector} onExpandPeriod={expandedPeriod ? () => selectFilters(expandedPeriod) : undefined} />
    <ObservationTable key={`${query}-${filters.provinceCode}`} records={monitoring.records} provinces={data?.provinceSnapshots ?? []} provinceCode={filters.provinceCode} pollutant={selectedPollutant} metricLabel={metric.label} unit={metric.unit} dataReady={dataReady} loading={loading} />
  </main>
}
