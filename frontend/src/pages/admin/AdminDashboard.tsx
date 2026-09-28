import { usePeriodMapSnapshots } from '../../hooks/usePeriodMapSnapshots'
import { useDashboardAnalytics } from '../../hooks/useDashboardAnalytics'
import { PollutionAnalytics } from '../../features/analytics/PollutionAnalytics'
import { startTransition, useMemo, useState } from 'react'
import { Button } from '../../components/ui/Button'
import { ComparisonPanel, type ComparisonValue } from '../../components/dashboard/ComparisonPanel'
import { DashboardBreadcrumb } from '../../components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from '../../components/dashboard/DashboardFilters'
import { KpiCard } from '../../components/dashboard/KpiCard'
import { PriorityAreasTable } from '../../components/dashboard/PriorityAreasTable'
import { DataState } from '../../components/dashboard/DataState'
import { HorizontalBarChart } from '../../features/analytics/HorizontalBarChart'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap, type MapMetric } from '../../features/geography/VietnamProvinceMap'
import { useAdminDashboardData } from '../../hooks/useAdminDashboardData'
import { buildAdminDashboardView } from '../../services/adminDashboardModel'
import type { DashboardFiltersValue } from '../../types/dashboard'
import { formatDecimal } from '../../utils/formatters'
import { Pagination } from '../../components/ui/Pagination'
import { usePagination } from '../../hooks/usePagination'
import './AdminDashboard.css'

const EMPTY_FILTERS: DashboardFiltersValue = {
  provinceCode: 'all', pollutant: 'pm25', year: 2025, month: 'all',
  startDate: '', endDate: '', sector: 'all',
}

export function AdminDashboard() {
  const { data, loading, error, retry } = useAdminDashboardData()
  const [filters, setFilters] = useState<DashboardFiltersValue>(EMPTY_FILTERS)
  const [filterControls, setFilterControls] = useState(EMPTY_FILTERS)
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const [mapMetric, setMapMetric] = useState<MapMetric>('pm25')
  const updateFilters = (next: DashboardFiltersValue | ((current: DashboardFiltersValue) => DashboardFiltersValue)) => {
    const nextFilters = typeof next === 'function' ? next(filterControls) : next
    setFilterControls(nextFilters)
    startTransition(() => setFilters(nextFilters))
  }
  const view = useMemo(() => buildAdminDashboardView(data, filters), [data, filters])
  const { currentYear, selectedPollutant, metric, scopeLabel } = view
  const controlPollutant = view.availableMetrics.includes(filterControls.pollutant) ? filterControls.pollutant : selectedPollutant
  const snapshots = data?.provinceSnapshots ?? []
  const activeFilters = { ...filters, pollutant: selectedPollutant }
  const analytics = useDashboardAnalytics(activeFilters, Boolean(data), data?.metadata?.generation)
  const mapSnapshots = usePeriodMapSnapshots(data, filters)
  const [comparisonSelection, setComparison] = useState<Partial<ComparisonValue>>({})
  const comparisonYear = view.years.find((year) => year !== currentYear) ?? currentYear ?? 0
  const comparisonProvince = snapshots.find((province) => province.provinceCode !== filters.provinceCode)?.provinceCode ?? snapshots[0]?.provinceCode ?? ''
  const comparison: ComparisonValue = { dimension: 'province', provinceCode: comparisonProvince, year: comparisonYear, ...comparisonSelection }
  const averageFor = (provinceCode: string | 'all', year: number | 'all', alignDatesToYear = false) => {
    const startDate = filters.startDate && alignDatesToYear && year !== 'all' ? `${year}${filters.startDate.slice(4)}` : filters.startDate
    const endDate = filters.endDate && alignDatesToYear && year !== 'all' ? `${year}${filters.endDate.slice(4)}` : filters.endDate
    const values = (data?.dashboardTrendRecords ?? []).filter((record) => {
      if (provinceCode !== 'all' && record.provinceCode !== provinceCode) return false
      if (year !== 'all' && Number(record.date.slice(0, 4)) !== year) return false
      if (filters.month !== 'all' && Number(record.date.slice(5, 7)) !== filters.month) return false
      if (startDate && record.date.slice(0, 7) < startDate.slice(0, 7)) return false
      if (endDate && record.date.slice(0, 7) > endDate.slice(0, 7)) return false
      return true
    }).map((record) => record[selectedPollutant]).filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
    return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
  }
  const currentComparisonValue = comparison.dimension === 'province'
    ? averageFor(filters.provinceCode, filters.year)
    : averageFor(filters.provinceCode, currentYear ?? 'all')
  const otherComparisonValue = comparison.dimension === 'province'
    ? averageFor(comparison.provinceCode, filters.year)
    : averageFor(filters.provinceCode, comparison.year, true)
  const comparisonPeriod = filters.month === 'all' ? '' : `Tháng ${filters.month} · `
  const currentComparisonLabel = comparison.dimension === 'province'
    ? scopeLabel
    : `${comparisonPeriod}${currentYear ?? 'Tất cả các năm'}`
  const otherComparisonLabel = comparison.dimension === 'province'
    ? snapshots.find((province) => province.provinceCode === comparison.provinceCode)?.provinceName ?? 'Tỉnh đối chiếu'
    : `${comparisonPeriod}${comparison.year}`
  const emissionPagination = usePagination(view.filteredEmissionRecords.length, JSON.stringify(filters))
  const visibleEmissions = view.filteredEmissionRecords.slice(emissionPagination.offset, emissionPagination.offset + emissionPagination.pageSize)
  const breadcrumbItems = [
    { id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((current) => ({ ...current, provinceCode: 'all' })) },
    ...(filters.provinceCode !== 'all' ? [{ id: 'province', label: scopeLabel }] : []),
    ...(filters.year !== 'all' ? [{ id: 'year', label: String(filters.year), onSelect: filters.month === 'all' ? undefined : () => setFilters(current => ({ ...current, month: 'all' })) }] : []),
    ...(filters.month !== 'all' ? [{ id: 'month', label: `Tháng ${filters.month}` }] : []),
  ]
  const periodLabel = filters.startDate || filters.endDate ? `${filters.startDate || 'Đầu kỳ'} → ${filters.endDate || 'Cuối kỳ'}` : `${filters.month === 'all' ? '' : `Tháng ${filters.month} · `}${filters.year === 'all' ? 'Tất cả các năm' : filters.year}`
  const yoyDirection = view.yoy === null ? 'neutral' : view.yoy > 0 ? 'up' : view.yoy < 0 ? 'down' : 'neutral'

  return (
    <main className="admin-dashboard mx-auto w-full max-w-[1440px] px-12 pt-9 pb-14 max-[1100px]:px-7 max-[1100px]:pt-7 max-[680px]:px-4 max-[680px]:pt-6">
      <header className="mb-6 flex items-center justify-between gap-6 max-[680px]:flex-col max-[680px]:items-start">
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-muted">AIR QUALITY INTELLIGENCE · VIỆT NAM</p>
          <h1 className="text-[clamp(1.4rem,2.6vw,1.85rem)] font-semibold tracking-tight text-heading">Chất lượng không khí</h1>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-surface px-3 py-2 text-xs text-muted">{data?.metadata?.source ?? (loading ? 'Đang tải nguồn dữ liệu' : 'Dữ liệu mock')}</span>
      </header>

      <DashboardBreadcrumb items={breadcrumbItems} />
      {error && <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft px-5 py-4 text-sm text-danger" role="alert"><span>{error}</span><Button onClick={retry}>Thử lại</Button></div>}
      {loading && <p role="status" className="mb-5 text-sm text-muted">Đang tải dữ liệu…</p>}
      {data?.metadata?.note && <p className="mb-5 text-xs leading-relaxed text-muted">{data.metadata.note}</p>}

      <div className="admin-dashboard__workspace">
        <aside className="admin-dashboard__filters" aria-label="Bộ lọc dashboard">
          <DashboardFilters value={{ ...filterControls, pollutant: controlPollutant }} years={view.years} pollutantOptions={view.pollutantOptions} dataReady={!loading && Boolean(data)} provinces={snapshots} sectors={data?.emissionSectors ?? []} onChange={updateFilters} onReset={() => updateFilters(EMPTY_FILTERS)} />
        </aside>
        <div className="admin-dashboard__content">
      <section className="admin-context" aria-label="Phạm vi tổng quan"><span>Phạm vi</span><strong>{scopeLabel}</strong><i aria-hidden="true">/</i><span>Kỳ báo cáo</span><strong>{periodLabel}</strong></section>

      <section className="kpi-grid" aria-label="Chỉ số điều hành chính" aria-busy={loading}>
        <KpiCard label="PM2.5 trung bình" value={formatDecimal(view.currentPm25, 'µg/m³')} detail={`${scopeLabel} · ${periodLabel}`} tone="yellow" />
        <KpiCard label="AQI trung bình" value={formatDecimal(view.currentAqi)} detail="Trung bình từ dữ liệu theo tháng" />
        <KpiCard label="YoY PM2.5" value={view.yoy === null ? 'Chưa có dữ liệu' : `${view.yoy > 0 ? '+' : ''}${view.yoy.toFixed(1)}%`} detail="So cùng tỉnh–tháng có đủ dữ liệu năm trước" trend={yoyDirection} />
        <KpiCard label="Ngày vượt ngưỡng" value={view.exceedanceDays === null ? 'Chưa có dữ liệu' : `${view.exceedanceDays} ngày`} detail="Theo dữ liệu backend cung cấp" />
        <KpiCard label="Tỉnh PM2.5 cao nhất" value={view.bestProvince?.label ?? 'Chưa có dữ liệu'} detail={view.bestProvince ? `${view.bestProvince.value.toFixed(1)} µg/m³` : 'Không có dữ liệu xếp hạng'} tone="red" />
        <KpiCard label="Tỉnh tăng nhanh nhất" value={view.fastestProvince?.provinceName ?? 'Chưa có dữ liệu'} detail={view.fastestProvince?.yearOverYearPercent == null ? 'Không có dữ liệu YoY' : `${view.fastestProvince.yearOverYearPercent > 0 ? '+' : ''}${view.fastestProvince.yearOverYearPercent.toFixed(1)}% YoY`} tone="red" />
        <KpiCard label="Tổng phát thải" value={view.totalEmissions === null ? 'Chưa có dữ liệu' : `${Math.round(view.totalEmissions).toLocaleString('vi-VN')} tấn`} detail="Dữ liệu phát thải theo kỳ đang chọn" tone="yellow" />
        <KpiCard label="Ngành phát thải lớn nhất" value={view.topSector?.label ?? 'Chưa có dữ liệu'} detail={view.topSector ? `${view.topSector.value.toLocaleString('vi-VN')} tấn` : 'Chưa có dữ liệu phát thải'} />
      </section>

      <section className="admin-visual-grid" aria-label="Bản đồ và xếp hạng không gian">
        <div className="admin-visual-grid__map"><VietnamProvinceMap provinceSnapshots={mapSnapshots} periodLabel={periodLabel} dataLoading={loading} dataError={error} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={mapMetric} layerVisible={mapLayerVisible} onMetricChange={(value) => { setMapMetric(value); if (value !== 'aqi') updateFilters((current) => ({ ...current, pollutant: value })) }} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={(province) => updateFilters((current) => ({ ...current, provinceCode: province.provinceCode }))} /></div>
        <div className="admin-visual-grid__provinces"><HorizontalBarChart eyebrow="Xếp hạng không gian" title="15 tỉnh có PM2.5 cao nhất" description="Xếp hạng PM2.5 trung bình theo kỳ đang chọn. Chọn một thanh để lọc dashboard theo tỉnh." points={view.provinceRanking.slice(0, 15)} unit="µg/m³" fileName={`top-tinh-pm25-${currentYear ?? 'all'}`} selectedId={filters.provinceCode === 'all' ? undefined : filters.provinceCode} onSelect={(point) => updateFilters((current) => ({ ...current, provinceCode: point.id }))} /></div>
      </section>

      <section className="admin-secondary-visual-grid" aria-label="Xu hướng và cơ cấu phát thải">
        <div className="admin-visual-grid__trend"><TrendChart title={`${metric.label} dài hạn · ${scopeLabel}`} description="Chuỗi thời gian theo tháng theo phạm vi và bộ lọc đang chọn." dataReady={Boolean(analytics.data)} loading={analytics.loading || Boolean(analytics.error)} points={(analytics.data?.timeline ?? []).map(point => { const values = (filters.provinceCode === 'all' ? Object.values(point.values) : [point.values[filters.provinceCode]]).filter((v): v is number => v != null); return { date: point.date, label: `${point.date.slice(5)}/${point.date.slice(2, 4)}`, value: values.length ? values.reduce((a, b) => a + b, 0) / values.length : null } })} onPointSelect={(point) => { if (point.date) updateFilters(current => ({ ...current, year: Number(point.date!.slice(0, 4)), month: Number(point.date!.slice(5)), startDate: '', endDate: '' })) }} metricLabel={metric.label} unit={metric.unit} fileName={`xu-huong-dai-han-${selectedPollutant}-${filters.provinceCode}`} /></div>
        <div className="admin-visual-grid__sectors"><HorizontalBarChart eyebrow="Cơ cấu nguồn thải" title="Xếp hạng ngành phát thải" description="Tổng phát thải theo ngành, theo các bộ lọc đang chọn." points={view.sectorRanking.slice(0, 5)} unit="tấn" fileName={`top-nganh-phat-thai-${currentYear ?? 'all'}`} selectedId={filters.sector === 'all' ? undefined : filters.sector} onSelect={(point) => updateFilters((current) => ({ ...current, sector: current.sector === point.id ? 'all' : point.id }))} /></div>
      </section>

      <ComparisonPanel years={view.years} dataReady={!loading && Boolean(data)} loading={loading} value={comparison} provinces={snapshots} currentLabel={currentComparisonLabel} comparisonLabel={otherComparisonLabel} currentValue={currentComparisonValue} comparisonValue={otherComparisonValue} unit={metric.unit} onChange={setComparison} />

      <details className="admin-emissions">
        <summary>Chi tiết phát thải theo tỉnh và ngành <span>({view.filteredEmissionRecords.length.toLocaleString('vi-VN')} bản ghi)</span></summary>
        <DataState compact isEmpty={view.filteredEmissionRecords.length === 0} emptyMessage="Không có số liệu phát thải trong phạm vi đang chọn.">
          <div className="admin-emissions__scroll" role="region" aria-label="Chi tiết phát thải" tabIndex={0}>
            <table>
              <thead><tr><th scope="col">Tỉnh / thành</th><th scope="col">Ngành phát thải</th><th scope="col">Năm</th><th scope="col">Tháng</th><th scope="col">Lượng phát thải (tấn)</th></tr></thead>
              <tbody>{visibleEmissions.map((record) => <tr key={`${record.provinceCode}-${record.year}-${record.month}-${record.sector}`}><td>{record.provinceName}</td><td>{record.sector}</td><td>{record.year}</td><td>{record.month}</td><td>{record.emissionTonnes.toLocaleString('vi-VN')}</td></tr>)}</tbody>
            </table>
          </div>
          <Pagination {...emissionPagination} label="Phân trang dữ liệu phát thải" itemLabel="bản ghi" />
        </DataState>
      </details>

      <PollutionAnalytics {...analytics} filters={activeFilters} onChange={updateFilters} onRetry={() => { retry(); analytics.retry() }} />

      <DataState isEmpty={!loading && view.priorityAreaRows.length === 0} emptyMessage="Backend chưa cung cấp khu vực ưu tiên cho bộ lọc hiện tại.">
        {view.priorityAreaRows.length > 0 && <PriorityAreasTable paginationScope={JSON.stringify(filters)} areas={view.priorityAreaRows} selectedProvinceCode={filters.provinceCode} onProvinceSelect={(provinceCode) => updateFilters((current) => ({ ...current, provinceCode }))} />}
      </DataState>
      <footer className="admin-disclaimer">Các chỉ số chỉ phản ánh những dữ liệu backend cung cấp. AQI, phát thải hoặc ngày vượt ngưỡng có thể để trống khi nguồn dữ liệu không có các trường đó.</footer>
        </div>
      </div>
    </main>
  )
}
