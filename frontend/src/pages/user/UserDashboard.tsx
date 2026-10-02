import { useCallback, useMemo, useState } from 'react'
import { DashboardBreadcrumb } from '../../components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from '../../components/dashboard/DashboardFilters'
import { DashboardIcon } from '../../components/dashboard/DashboardIcon'
import { AQISummaryCard } from '../../components/dashboard/AQISummaryCard'
import { PollutantMetrics } from '../../components/dashboard/PollutantMetrics'
import { Button } from '../../components/ui/Button'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap } from '../../features/geography/VietnamProvinceMap'
import { useDashboardData } from '../../hooks/useDashboardData'
import { buildMonitoringView, DEFAULT_FILTERS, hasPeriodFilter, metricOptions, periodLabel } from '../../services/dashboardSelectors'
import type { DashboardFiltersValue, Pollutant, ProvinceSnapshot } from '../../types/dashboard'

export default function UserDashboard() {
  const { data, loading, error, retry } = useDashboardData()
  const [selection, setFilters] = useState<DashboardFiltersValue>(DEFAULT_FILTERS)
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const options = useMemo(() => metricOptions(data, true), [data])
  const pollutant = options.some((option) => option.value === selection.pollutant) ? selection.pollutant : options[0]?.value ?? 'pm25'
  const filters = useMemo(() => ({ ...selection, pollutant }), [selection, pollutant])
  const current = !hasPeriodFilter(filters)
  const view = useMemo(() => buildMonitoringView(data, filters, current), [data, filters, current])
  const years = useMemo(() => [...new Set(data?.dashboardTrendRecords.map((record) => Number(record.date.slice(0, 4))) ?? [])].sort((a, b) => b - a), [data])
  const selectProvince = useCallback((province: ProvinceSnapshot) => setFilters((value) => ({ ...value, provinceCode: province.provinceCode })), [])
  const selectPollutant = useCallback((next: Pollutant) => setFilters((value) => ({ ...value, pollutant: next })), [])
  const period = current ? 'Bản ghi mới nhất' : periodLabel(filters)

  return <main className="mx-auto w-full max-w-[1800px] px-8 pt-6 pb-8 max-md:px-4 max-md:pt-4">
    <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="rounded-xl border border-accent-border bg-accent-soft p-3 text-accent"><DashboardIcon name="air" /></span>
        <div><p className="text-[.7rem] font-semibold tracking-wider text-muted">AIR QUALITY · VIỆT NAM</p><h1 className="mt-1 text-2xl font-semibold tracking-tight text-heading">Chất lượng không khí</h1></div>
      </div>
      <span className="rounded-full border border-border px-3 py-1.5 text-xs text-muted">{data?.metadata?.source ?? 'Theo dõi không khí'}</span>
    </header>
    <DashboardBreadcrumb items={[{ id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((value) => ({ ...value, provinceCode: 'all' })) }, ...(filters.provinceCode === 'all' ? [] : [{ id: 'province', label: view.scopeLabel }])]} />
    {error && <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft p-4 text-sm text-danger"><p>{error}</p><Button onClick={retry}>Thử lại</Button></div>}
    {loading && <p role="status" className="mb-3 text-xs text-muted">Đang tải số liệu. Bản đồ vẫn có thể sử dụng.</p>}
    <DashboardFilters variant="user" value={filters} years={years} pollutantOptions={options} dataReady={Boolean(data)} provinces={data?.provinceSnapshots ?? []} onChange={setFilters} onReset={() => setFilters(DEFAULT_FILTERS)} />
    <div className="grid grid-cols-[minmax(0,2.5fr)_minmax(270px,1fr)] items-start gap-4 max-[1023px]:grid-cols-1">
      <VietnamProvinceMap variant="user" provinceSnapshots={view.snapshots} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={pollutant} periodLabel={period} layerVisible={mapLayerVisible} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={selectProvince} />
      <aside className="grid min-w-0 gap-4 max-[1023px]:grid-cols-2 max-[640px]:grid-cols-1">
        <AQISummaryCard aqi={view.aqi} scopeLabel={view.scopeLabel} period={period} snapshotDate={current ? data?.metadata?.snapshotDate : null} loading={loading} />
        <section className="min-w-0" aria-label="Các chất ô nhiễm chính"><h2 className="mb-3 text-sm font-semibold text-heading">Chất ô nhiễm chính</h2><PollutantMetrics metrics={view.metrics} metadata={data?.metadata?.metrics} selected={pollutant} onSelect={selectPollutant} /><p className="mt-2 text-[.7rem] leading-relaxed text-muted">{current ? 'Giá trị từ bản ghi mới nhất; trường chưa có được để trống.' : 'Nồng độ trung bình trong kỳ đang chọn.'}</p></section>
        <p className="rounded-lg border border-border bg-surface-subtle p-3 text-xs leading-relaxed text-muted max-[1023px]:col-span-full">Chọn tỉnh trên bản đồ để xem thông tin khu vực. Màu nồng độ và mức AQI có chú giải riêng.</p>
      </aside>
    </div>
    <div className="mt-4"><TrendChart dataReady={Boolean(data)} loading={loading} title={`${view.metric.label} · ${view.scopeLabel}`} description="Trung bình theo tháng. Bản ghi mới nhất hiển thị xu hướng 12 tháng gần nhất; chọn năm hoặc khoảng ngày để xem lịch sử." points={current ? view.chartPoints.slice(-12) : view.chartPoints} metricLabel={view.metric.label} unit={view.metric.unit} fileName={`xu-huong-${pollutant}-${filters.provinceCode}`} /></div>
    {data?.metadata?.note && <details className="mt-4 text-xs leading-relaxed text-muted"><summary className="cursor-pointer">Thông tin nguồn dữ liệu</summary><p className="mt-2">{data.metadata.note}</p></details>}
  </main>
}
