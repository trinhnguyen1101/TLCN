import { useCallback, useMemo, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { DashboardBreadcrumb } from '../../components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from '../../components/dashboard/DashboardFilters'
import { KpiCard } from '../../components/dashboard/KpiCard'
import { HorizontalBarChart } from '../../features/analytics/HorizontalBarChart'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap } from '../../features/geography/VietnamProvinceMap'
import { aqiLevel } from '../../features/geography/mapColorScale'
import { useAdminDashboardData } from '../../hooks/useAdminDashboardData'
import { buildAdminDashboardView } from '../../services/adminDashboardModel'
import { DEFAULT_FILTERS, periodLabel } from '../../services/dashboardSelectors'
import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../types/dashboard'
import { formatDecimal } from '../../utils/formatters'
import { AdminAnalytics } from './AdminAnalytics'

export function AdminDashboard() {
  const { data, loading, error, retry } = useAdminDashboardData()
  const [selection, setFilters] = useState<Partial<DashboardFiltersValue>>({})
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const [tab, setTab] = useState('overview')
  const scope = useMemo(() => ({ ...DEFAULT_FILTERS, year: data?.dashboardTrendRecords.reduce((latest, record) => Math.max(latest, Number(record.date.slice(0, 4))), 0) || 'all' as const, ...selection }), [data, selection])
  const view = useMemo(() => buildAdminDashboardView(data, scope), [data, scope])
  const filters = useMemo(() => ({ ...scope, pollutant: view.selectedPollutant }), [scope, view.selectedPollutant])
  const { monitoring, metric, scopeLabel, selectedPollutant } = view
  const selectProvinceCode = useCallback((provinceCode: string) => setFilters((current) => ({ ...current, provinceCode })), [])
  const selectProvince = useCallback((province: ProvinceSnapshot) => selectProvinceCode(province.provinceCode), [selectProvinceCode])
  const selectPollutant = useCallback((pollutant: Pollutant) => setFilters((current) => ({ ...current, pollutant })), [])
  const selectSector = useCallback((sector: string) => setFilters((current) => ({ ...current, sector: current.sector === sector ? 'all' : sector })), [])
  const period = periodLabel(filters)
  const aqi = aqiLevel(view.currentAqi)

  return <main className="mx-auto w-full max-w-[1800px] px-8 pt-6 pb-8 max-md:px-4 max-md:pt-4">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div><p className="text-[.7rem] font-semibold tracking-wider text-muted">AIR QUALITY INTELLIGENCE · ADMIN</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-heading">Tổng quan điều hành</h1></div>
      <span className="rounded-full border border-border px-3 py-1.5 text-xs text-muted">{data?.metadata?.source ?? 'Giám sát & phân tích'}</span>
    </header>
    <DashboardBreadcrumb items={[{ id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => selectProvinceCode('all') }, ...(filters.provinceCode === 'all' ? [] : [{ id: 'province', label: scopeLabel }]), { id: 'period', label: period }]} />
    {error && <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft p-4 text-sm text-danger" role="alert"><span>{error}</span><Button onClick={retry}>Thử lại</Button></div>}
    {loading && <p role="status" className="mb-3 text-xs text-muted">Đang tải dữ liệu quản lý…</p>}
    <DashboardFilters variant="admin" value={filters} years={view.years} pollutantOptions={view.pollutantOptions} dataReady={Boolean(data)} provinces={data?.provinceSnapshots ?? []} sectors={data?.emissionSectors ?? []} onChange={setFilters} onReset={() => setFilters({})} />
    <section className="mb-4 grid grid-cols-5 gap-3 max-[1199px]:grid-cols-3 max-md:grid-cols-2" aria-label="Chỉ số điều hành chính" aria-busy={loading}>
      <KpiCard icon="chart" label={`${metric.label} trung bình`} value={formatDecimal(monitoring.metrics[selectedPollutant], metric.unit)} detail={scopeLabel} tone="yellow" loading={loading} />
      <KpiCard icon="air" label="AQI trung bình" value={formatDecimal(view.currentAqi)} detail={aqi?.label ?? 'Nguồn chưa cung cấp AQI'} valueColor={aqi?.color} loading={loading} />
      <KpiCard icon="location" label={`Tỉnh có ${metric.label} cao nhất`} value={monitoring.ranking[0]?.label ?? 'Chưa có dữ liệu'} detail={monitoring.ranking[0] ? formatDecimal(monitoring.ranking[0].value, metric.unit) : period} loading={loading} />
      <KpiCard icon="layers" label={`Tỉnh có dữ liệu ${metric.label}`} value={data ? `${monitoring.reportingProvinces}` : 'Chưa có dữ liệu'} detail="Trong phạm vi bộ lọc" loading={loading} />
      <KpiCard icon="chart" label="YoY PM2.5" value={view.yoy === null ? 'Chưa có dữ liệu' : `${view.yoy > 0 ? '+' : ''}${view.yoy.toFixed(1)}%`} detail={filters.year === 'all' ? 'Chọn một năm để so sánh cùng kỳ' : `So với cùng kỳ ${filters.year - 1}`} trend={view.yoy === null ? 'neutral' : view.yoy > 0 ? 'up' : 'down'} loading={loading} />
    </section>
    <section className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] items-stretch gap-4 max-[1023px]:grid-cols-1" aria-label="Giám sát không gian và thời gian">
      <VietnamProvinceMap variant="admin" provinceSnapshots={monitoring.snapshots} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={selectedPollutant} periodLabel={period} layerVisible={mapLayerVisible} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={selectProvince} />
      <div className="grid min-w-0 content-start gap-4 max-[1023px]:grid-cols-2 max-md:grid-cols-1">
        <TrendChart compact dataReady={Boolean(data)} loading={loading} title={`${metric.label} · ${scopeLabel}`} description="Giá trị trung bình theo tháng trong phạm vi bộ lọc." points={view.chartPoints} metricLabel={metric.label} unit={metric.unit} fileName={`xu-huong-${selectedPollutant}-${filters.provinceCode}`} />
        <HorizontalBarChart compact dataReady={Boolean(data)} loading={loading} eyebrow="So sánh khu vực" title={`Top tỉnh theo ${metric.label}`} description="Nồng độ trung bình theo kỳ đang chọn. Chọn một thanh để lọc tỉnh." points={monitoring.ranking.slice(0, 5)} unit={metric.unit} fileName={`top-tinh-${selectedPollutant}`} selectedId={filters.provinceCode} onSelect={(point) => selectProvinceCode(point.id)} />
      </div>
    </section>
    <AdminAnalytics data={data} filters={filters} view={view} loading={loading} tab={tab} onTabChange={setTab} onProvinceSelect={selectProvinceCode} onPollutantSelect={selectPollutant} onSectorSelect={selectSector} />
  </main>
}
