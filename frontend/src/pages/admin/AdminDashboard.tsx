import { useMemo, useState } from 'react'
import { Button } from '../../components/ui/Button'
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
import './AdminDashboard.css'

const EMPTY_FILTERS: DashboardFiltersValue = {
  provinceCode: 'all', pollutant: 'pm25', year: 'all', month: 'all',
  startDate: '', endDate: '', sector: 'all',
}

export function AdminDashboard() {
  const { data, loading, error, retry } = useAdminDashboardData()
  const [filters, setFilters] = useState<DashboardFiltersValue>(EMPTY_FILTERS)
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const [mapMetric, setMapMetric] = useState<MapMetric>('pm25')
  const view = useMemo(() => buildAdminDashboardView(data, filters), [data, filters])
  const { currentYear, selectedPollutant, metric, scopeLabel } = view
  const snapshots = data?.provinceSnapshots ?? []
  const activeFilters = { ...filters, pollutant: selectedPollutant }
  const breadcrumbItems = [
    { id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((current) => ({ ...current, provinceCode: 'all' })) },
    ...(filters.provinceCode !== 'all' ? [{ id: 'province', label: scopeLabel }] : []),
    ...(filters.year !== 'all' ? [{ id: 'year', label: String(filters.year) }] : []),
    ...(filters.month !== 'all' ? [{ id: 'month', label: `Tháng ${filters.month}` }] : []),
  ]
  const periodLabel = `${filters.month === 'all' ? 'Cả năm' : `Tháng ${filters.month}`} ${currentYear ?? '—'}`
  const yoyDirection = view.yoy === null ? 'neutral' : view.yoy > 0 ? 'up' : view.yoy < 0 ? 'down' : 'neutral'

  return (
    <main className="admin-dashboard mx-auto w-full max-w-[1440px] px-12 pt-9 pb-14 max-[1100px]:px-7 max-[1100px]:pt-7 max-[680px]:px-4 max-[680px]:pt-6">
      <header className="mb-6 flex items-center justify-between gap-6 max-[680px]:flex-col max-[680px]:items-start">
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-muted">AIR QUALITY INTELLIGENCE · ADMIN</p>
          <h1 className="text-[clamp(1.4rem,2.6vw,1.85rem)] font-semibold tracking-tight text-heading">Tổng quan điều hành</h1>
          <p className="mt-2 max-w-3xl text-sm text-secondary">Theo dõi chất lượng không khí, xu hướng và nguồn phát thải trên một màn hình.</p>
        </div>
        <span className="shrink-0 rounded-full border border-border bg-surface px-3 py-2 text-xs text-muted">{data?.metadata?.source ?? (loading ? 'Đang tải nguồn dữ liệu' : 'Dữ liệu mock')}</span>
      </header>

      <DashboardBreadcrumb items={breadcrumbItems} />
      {error && <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-card border border-danger/25 bg-danger-soft px-5 py-4 text-sm text-danger" role="alert"><span>{error}</span><Button onClick={retry}>Thử lại</Button></div>}
      {loading && <p role="status" className="mb-5 text-sm text-muted">Đang tải dữ liệu quản lý…</p>}
      {data?.metadata?.note && <p className="mb-5 text-xs leading-relaxed text-muted">{data.metadata.note}</p>}

      <DashboardFilters value={activeFilters} years={view.years} pollutantOptions={view.pollutantOptions} dataReady={!loading && Boolean(data)} provinces={snapshots} sectors={data?.emissionSectors ?? []} onChange={setFilters} onReset={() => setFilters(EMPTY_FILTERS)} />
      <section className="admin-context" aria-label="Phạm vi tổng quan"><span>Phạm vi</span><strong>{scopeLabel}</strong><i aria-hidden="true">/</i><span>Kỳ báo cáo</span><strong>{periodLabel}</strong></section>

      <section className="kpi-grid" aria-label="Chỉ số điều hành chính" aria-busy={loading}>
        <KpiCard label="PM2.5 trung bình" value={formatDecimal(view.currentPm25, 'µg/m³')} detail={`${scopeLabel} · ${periodLabel}`} tone="yellow" />
        <KpiCard label="AQI trung bình" value={formatDecimal(view.currentAqi)} detail="Trung bình từ dữ liệu theo tháng" />
        <KpiCard label="YoY PM2.5" value={view.yoy === null ? 'Chưa có dữ liệu' : `${view.yoy > 0 ? '+' : ''}${view.yoy.toFixed(1)}%`} detail={`So với cùng kỳ ${currentYear ? currentYear - 1 : 'trước đó'}`} trend={yoyDirection} />
        <KpiCard label="Ngày vượt ngưỡng" value={view.exceedanceDays === null ? 'Chưa có dữ liệu' : `${view.exceedanceDays} ngày`} detail="Theo dữ liệu backend cung cấp" />
        <KpiCard label="Tỉnh PM2.5 cao nhất" value={view.bestProvince?.label ?? 'Chưa có dữ liệu'} detail={view.bestProvince ? `${view.bestProvince.value.toFixed(1)} µg/m³` : 'Không có dữ liệu xếp hạng'} tone="red" />
        <KpiCard label="Tỉnh tăng nhanh nhất" value={view.fastestProvince?.provinceName ?? 'Chưa có dữ liệu'} detail={view.fastestProvince?.yearOverYearPercent == null ? 'Không có dữ liệu YoY' : `${view.fastestProvince.yearOverYearPercent > 0 ? '+' : ''}${view.fastestProvince.yearOverYearPercent.toFixed(1)}% YoY`} tone="red" />
        <KpiCard label="Tổng phát thải" value={view.totalEmissions === null ? 'Chưa có dữ liệu' : `${Math.round(view.totalEmissions).toLocaleString('vi-VN')} tấn`} detail="Dữ liệu phát thải theo kỳ đang chọn" tone="yellow" />
        <KpiCard label="Ngành phát thải lớn nhất" value={view.topSector?.label ?? 'Chưa có dữ liệu'} detail={view.topSector ? `${view.topSector.value.toLocaleString('vi-VN')} tấn` : 'Chưa có dữ liệu phát thải'} />
      </section>

      <section className="admin-visual-grid" aria-label="Phân tích điều hành">
        <div className="admin-visual-grid__map"><VietnamProvinceMap provinceSnapshots={snapshots} metricMetadata={data?.metadata?.metrics} selectedProvinceCode={filters.provinceCode} metric={mapMetric} layerVisible={mapLayerVisible} onMetricChange={setMapMetric} onLayerVisibilityChange={setMapLayerVisible} onProvinceSelect={(province) => setFilters((current) => ({ ...current, provinceCode: province.provinceCode }))} /></div>
        <div className="admin-visual-grid__provinces"><HorizontalBarChart eyebrow="Xếp hạng không gian" title="Top tỉnh theo PM2.5" description="Xếp hạng PM2.5 trung bình theo kỳ đang chọn. Chọn một thanh để lọc dashboard theo tỉnh." points={view.provinceRanking.slice(0, 5)} unit="µg/m³" fileName={`top-tinh-pm25-${currentYear ?? 'all'}`} selectedId={filters.provinceCode === 'all' ? undefined : filters.provinceCode} onSelect={(point) => setFilters((current) => ({ ...current, provinceCode: point.id }))} /></div>
        <div className="admin-visual-grid__trend"><TrendChart title={`${metric.label} dài hạn · ${scopeLabel}`} description="Chuỗi thời gian theo tháng theo phạm vi và bộ lọc đang chọn." points={view.chartPoints} metricLabel={metric.label} unit={metric.unit} fileName={`xu-huong-dai-han-${selectedPollutant}-${filters.provinceCode}`} /></div>
        <div className="admin-visual-grid__sectors"><HorizontalBarChart eyebrow="Cơ cấu nguồn thải" title="Top ngành phát thải" description="Tổng phát thải theo ngành trong phạm vi hiện tại." points={view.sectorRanking.slice(0, 5)} unit="tấn" fileName={`top-nganh-phat-thai-${currentYear ?? 'all'}`} selectedId={filters.sector === 'all' ? undefined : filters.sector} onSelect={(point) => setFilters((current) => ({ ...current, sector: current.sector === point.id ? 'all' : point.id }))} /></div>
      </section>

      <DataState isEmpty={!loading && view.priorityAreaRows.length === 0} emptyMessage="Backend chưa cung cấp khu vực ưu tiên cho bộ lọc hiện tại.">
        {view.priorityAreaRows.length > 0 && <PriorityAreasTable areas={view.priorityAreaRows} selectedProvinceCode={filters.provinceCode} onProvinceSelect={(provinceCode) => setFilters((current) => ({ ...current, provinceCode }))} />}
      </DataState>
      <footer className="admin-disclaimer">Các chỉ số chỉ phản ánh những dữ liệu backend cung cấp. AQI, phát thải hoặc ngày vượt ngưỡng có thể để trống khi nguồn dữ liệu không có các trường đó.</footer>
    </main>
  )
}
