import { useMemo, useState } from 'react'
import { DashboardBreadcrumb } from '../../components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from '../../components/dashboard/DashboardFilters'
import { KpiCard } from '../../components/dashboard/KpiCard'
import { PriorityAreasTable } from '../../components/dashboard/PriorityAreasTable'
import { HorizontalBarChart, type HorizontalBarPoint } from '../../features/analytics/HorizontalBarChart'
import { TrendChart } from '../../features/analytics/TrendChart'
import { VietnamProvinceMap, type MapMetric } from '../../features/geography/VietnamProvinceMap'
import {
  annualProvinceSummaries,
  dashboardTrendRecords,
  emissionRecords,
  emissionSectors,
  priorityAreas,
  provinceSnapshots,
} from '../../services/mockDashboardData'
import type { ChartPoint, DashboardFiltersValue, DashboardTrendRecord, PriorityArea, ProvinceCode } from '../../types/dashboard'
import { formatDecimal } from '../../utils/formatters'
import './AdminDashboard.css'

const LATEST_YEAR = 2026

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
}

const mean = (values: number[]) => values.length > 0
  ? values.reduce((sum, value) => sum + value, 0) / values.length
  : null

const dateForYear = (date: string, year: number) => date ? `${year}${date.slice(4)}` : ''

function matchesPeriod(record: DashboardTrendRecord, filters: DashboardFiltersValue, year?: number, provinceCode = filters.provinceCode) {
  if (provinceCode !== 'all' && record.provinceCode !== provinceCode) return false
  if (year !== undefined && Number(record.date.slice(0, 4)) !== year) return false
  if (filters.year !== 'all' && year === undefined && Number(record.date.slice(0, 4)) !== filters.year) return false
  if (filters.month !== 'all' && Number(record.date.slice(5, 7)) !== filters.month) return false

  const startDate = year === undefined ? filters.startDate : dateForYear(filters.startDate, year)
  const endDate = year === undefined ? filters.endDate : dateForYear(filters.endDate, year)
  if (startDate && record.date < startDate) return false
  if (endDate && record.date > endDate) return false
  return true
}

function groupProvinceValues(records: DashboardTrendRecord[], key: 'pm25' | 'aqi') {
  const grouped = new Map<ProvinceCode, number[]>()
  records.forEach((record) => grouped.set(record.provinceCode, [...(grouped.get(record.provinceCode) ?? []), record[key]]))
  return new Map([...grouped].map(([code, values]) => [code, mean(values) ?? 0]))
}

const trendFromChange = (change: number): PriorityArea['trend'] => {
  if (change >= 8) return 'up'
  if (change > 2) return 'slight-up'
  if (change <= -2) return 'down'
  return 'steady'
}

export function AdminDashboard() {
  const [filters, setFilters] = useState<DashboardFiltersValue>(DEFAULT_FILTERS)
  const [mapMetric, setMapMetric] = useState<MapMetric>('aqi')
  const [mapLayerVisible, setMapLayerVisible] = useState(true)
  const currentYear = filters.year === 'all' ? LATEST_YEAR : filters.year
  const metric = metricMeta[filters.pollutant]

  const provinceName = (code: string) => provinceSnapshots.find((province) => province.provinceCode === code)?.provinceName ?? 'Toàn quốc'
  const scopeLabel = provinceName(filters.provinceCode)

  const trendRecords = useMemo(
    () => dashboardTrendRecords.filter((record) => matchesPeriod(record, filters)),
    [filters],
  )

  const currentRecords = useMemo(
    () => dashboardTrendRecords.filter((record) => matchesPeriod(record, filters, currentYear)),
    [currentYear, filters],
  )

  const previousRecords = useMemo(
    () => dashboardTrendRecords.filter((record) => matchesPeriod(record, filters, currentYear - 1)),
    [currentYear, filters],
  )

  const chartPoints: ChartPoint[] = useMemo(() => {
    const grouped = new Map<string, number[]>()
    trendRecords.forEach((record) => grouped.set(record.date.slice(0, 7), [...(grouped.get(record.date.slice(0, 7)) ?? []), record[filters.pollutant]]))
    return [...grouped.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, values]) => ({
        label: filters.year === 'all' ? `T${Number(date.slice(5))}/${date.slice(2, 4)}` : `T${Number(date.slice(5))}`,
        value: Number((mean(values) ?? 0).toFixed(1)),
      }))
  }, [filters.pollutant, filters.year, trendRecords])

  const currentProvincePm25 = useMemo(() => groupProvinceValues(currentRecords, 'pm25'), [currentRecords])
  const previousProvincePm25 = useMemo(() => groupProvinceValues(previousRecords, 'pm25'), [previousRecords])

  const provinceRanking = useMemo<HorizontalBarPoint[]>(() => [...currentProvincePm25]
    .map(([code, value]) => ({ id: code, label: provinceName(code), value: Number(value.toFixed(1)) }))
    .sort((a, b) => b.value - a.value), [currentProvincePm25])

  const provinceGrowth = useMemo(() => provinceRanking
    .map((province) => {
      const previous = previousProvincePm25.get(province.id as ProvinceCode)
      const fallback = annualProvinceSummaries.find((summary) => summary.provinceCode === province.id && summary.year === currentYear)?.yearOverYearPercent ?? null
      const change = previous && previous !== 0 ? ((province.value - previous) / previous) * 100 : fallback
      return { ...province, change }
    })
    .filter((province) => province.change !== null)
    .sort((a, b) => (b.change ?? 0) - (a.change ?? 0)), [currentYear, previousProvincePm25, provinceRanking])

  const currentPm25Average = mean(currentRecords.map((record) => record.pm25))
  const currentAqiAverage = mean(currentRecords.map((record) => record.aqi))
  const previousPm25Average = mean(previousRecords.map((record) => record.pm25))
  const fallbackYoy = mean(annualProvinceSummaries
    .filter((summary) => summary.year === currentYear && (filters.provinceCode === 'all' || summary.provinceCode === filters.provinceCode))
    .map((summary) => summary.yearOverYearPercent))
  const yoyChange = currentPm25Average !== null && previousPm25Average !== null && previousPm25Average !== 0
    ? ((currentPm25Average - previousPm25Average) / previousPm25Average) * 100
    : fallbackYoy

  const summaryScope = annualProvinceSummaries.filter((summary) => summary.year === currentYear && (filters.provinceCode === 'all' || summary.provinceCode === filters.provinceCode))
  const visibleMonthCount = new Set(currentRecords.map((record) => record.date.slice(0, 7))).size
  const annualExceedanceAverage = mean(summaryScope.map((summary) => summary.exceedanceDays))
  const exceedanceDays = annualExceedanceAverage === null || currentRecords.length === 0
    ? null
    : Math.round(annualExceedanceAverage * (visibleMonthCount / 12))

  const filteredEmissions = useMemo(() => emissionRecords.filter((record) => {
    if (record.year !== currentYear) return false
    if (filters.provinceCode !== 'all' && record.provinceCode !== filters.provinceCode) return false
    if (filters.month !== 'all' && record.month !== filters.month) return false
    if (filters.sector !== 'all' && record.sector !== filters.sector) return false

    const recordDate = `${record.year}-${String(record.month).padStart(2, '0')}-15`
    const startDate = dateForYear(filters.startDate, currentYear)
    const endDate = dateForYear(filters.endDate, currentYear)
    if (startDate && recordDate < startDate) return false
    if (endDate && recordDate > endDate) return false
    return true
  }), [currentYear, filters.endDate, filters.month, filters.provinceCode, filters.sector, filters.startDate])

  const sectorRanking = useMemo<HorizontalBarPoint[]>(() => {
    const totals = new Map<string, number>()
    filteredEmissions.forEach((record) => totals.set(record.sector, (totals.get(record.sector) ?? 0) + record.emissionTonnes))
    return [...totals]
      .map(([sector, value]) => ({ id: sector, label: sector, value: Math.round(value) }))
      .sort((a, b) => b.value - a.value)
  }, [filteredEmissions])

  const totalEmissions = filteredEmissions.length > 0
    ? Math.round(filteredEmissions.reduce((sum, record) => sum + record.emissionTonnes, 0))
    : null

  const priorityAreaRows = useMemo<PriorityArea[]>(() => priorityAreas
    .filter((area) => filters.provinceCode === 'all' || area.provinceCode === filters.provinceCode)
    .flatMap((area) => {
      const provinceCurrentRecords = currentRecords.filter((record) => record.provinceCode === area.provinceCode)
      if (provinceCurrentRecords.length === 0) return []

      const provincePreviousRecords = previousRecords.filter((record) => record.provinceCode === area.provinceCode)
      const pm25Average = mean(provinceCurrentRecords.map((record) => record.pm25))
      const selectedMetricAverage = mean(provinceCurrentRecords.map((record) => record[filters.pollutant]))
      const selectedMetricPreviousAverage = mean(provincePreviousRecords.map((record) => record[filters.pollutant]))
      const summary = annualProvinceSummaries.find((item) => item.provinceCode === area.provinceCode && item.year === currentYear)
      const isFullLatestPeriod = currentYear === LATEST_YEAR && filters.month === 'all' && !filters.startDate && !filters.endDate
      const yearOverYearPercent = isFullLatestPeriod && filters.pollutant === 'pm25'
        ? area.yearOverYearPercent
        : selectedMetricAverage !== null && selectedMetricPreviousAverage !== null && selectedMetricPreviousAverage !== 0
          ? ((selectedMetricAverage - selectedMetricPreviousAverage) / selectedMetricPreviousAverage) * 100
          : filters.pollutant === 'pm25' ? (summary?.yearOverYearPercent ?? 0) : 0
      const visibleProvinceMonthCount = new Set(provinceCurrentRecords.map((record) => record.date.slice(0, 7))).size
      const annualExceedanceDays = currentYear === LATEST_YEAR ? area.exceedanceDays : (summary?.exceedanceDays ?? area.exceedanceDays)
      const provinceEmissions = filteredEmissions.filter((record) => record.provinceCode === area.provinceCode)
      const sectorTotals = new Map<string, number>()
      provinceEmissions.forEach((record) => sectorTotals.set(record.sector, (sectorTotals.get(record.sector) ?? 0) + record.emissionTonnes))
      const mainEmissionSector = [...sectorTotals].sort(([, a], [, b]) => b - a)[0]?.[0] ?? null

      return [{
        ...area,
        pm25Average: isFullLatestPeriod ? area.pm25Average : Number((pm25Average ?? area.pm25Average).toFixed(1)),
        yearOverYearPercent: Number(yearOverYearPercent.toFixed(1)),
        exceedanceDays: Math.round(annualExceedanceDays * (visibleProvinceMonthCount / 12)),
        totalEmissions: provinceEmissions.length > 0
          ? Math.round(provinceEmissions.reduce((sum, record) => sum + record.emissionTonnes, 0))
          : null,
        mainEmissionSector,
        trend: trendFromChange(yearOverYearPercent),
      }]
    }), [currentRecords, currentYear, filteredEmissions, filters.endDate, filters.month, filters.pollutant, filters.provinceCode, filters.startDate, previousRecords])

  const topProvince = provinceRanking[0]
  const fastestProvince = provinceGrowth[0]
  const topSector = sectorRanking[0]

  const breadcrumbItems = [
    { id: 'country', label: 'Việt Nam', onSelect: filters.provinceCode === 'all' ? undefined : () => setFilters((current) => ({ ...current, provinceCode: 'all' })) },
    ...(filters.provinceCode !== 'all' ? [{ id: 'province', label: scopeLabel }] : []),
    ...(filters.year !== 'all' ? [{ id: 'year', label: String(filters.year), onSelect: filters.month === 'all' ? undefined : () => setFilters((current) => ({ ...current, month: 'all' })) }] : []),
    ...(filters.month !== 'all' ? [{ id: 'month', label: `Tháng ${filters.month}` }] : []),
  ]

  const periodLabel = `${filters.month === 'all' ? 'Cả năm' : `Tháng ${filters.month}`} ${currentYear}`
  const yoyDirection = yoyChange === null ? 'neutral' : yoyChange > 0 ? 'up' : yoyChange < 0 ? 'down' : 'neutral'

  return (
    <main className="app-shell admin-dashboard">
      <header className="app-header">
        <div>
          <p>Air Quality Intelligence · Admin</p>
          <h1>Tổng quan điều hành</h1>
          <span>Theo dõi chất lượng không khí, xu hướng và nguồn phát thải trên một màn hình.</span>
        </div>
        <span className="demo-badge">Dữ liệu minh họa</span>
      </header>

      <DashboardFilters value={filters} provinces={provinceSnapshots} sectors={emissionSectors} onChange={setFilters} onReset={() => setFilters(DEFAULT_FILTERS)} />
      <DashboardBreadcrumb items={breadcrumbItems} />

      <section className="admin-context" aria-label="Phạm vi tổng quan">
        <span>Phạm vi</span><strong>{scopeLabel}</strong><i aria-hidden="true">/</i><span>Kỳ báo cáo</span><strong>{periodLabel}</strong>
      </section>

      <section className="kpi-grid" aria-label="Chỉ số điều hành chính">
        <KpiCard label="PM2.5 trung bình" value={formatDecimal(currentPm25Average, 'µg/m³')} detail={`${scopeLabel} · ${periodLabel}`} tone="yellow" />
        <KpiCard label="AQI trung bình" value={formatDecimal(currentAqiAverage)} detail="Trung bình từ dữ liệu theo tháng" />
        <KpiCard label="YoY PM2.5" value={yoyChange === null ? 'Chưa có dữ liệu' : `${yoyChange > 0 ? '+' : ''}${yoyChange.toFixed(1)}%`} detail={`So với cùng kỳ ${currentYear - 1}`} trend={yoyDirection} />
        <KpiCard label="Ngày vượt ngưỡng" value={exceedanceDays === null ? 'Chưa có dữ liệu' : `${exceedanceDays} ngày`} detail="Ước tính từ dữ liệu demo" />
        <KpiCard label="Tỉnh PM2.5 cao nhất" value={topProvince?.label ?? 'Chưa có dữ liệu'} detail={topProvince ? `${topProvince.value.toFixed(1)} µg/m³` : 'Không có dữ liệu xếp hạng'} tone="red" />
        <KpiCard label="Tỉnh tăng nhanh nhất" value={fastestProvince?.label ?? 'Chưa có dữ liệu'} detail={fastestProvince?.change === null || fastestProvince === undefined ? 'Không có dữ liệu YoY' : `${(fastestProvince.change ?? 0) > 0 ? '+' : ''}${(fastestProvince.change ?? 0).toFixed(1)}% YoY`} tone="red" />
        <KpiCard label="Tổng phát thải" value={totalEmissions === null ? 'Chưa có dữ liệu' : `${totalEmissions.toLocaleString('vi-VN')} tấn`} detail="PM2.5 · dữ liệu tổng hợp demo" tone="yellow" />
        <KpiCard label="Ngành phát thải lớn nhất" value={topSector?.label ?? 'Chưa có dữ liệu'} detail={topSector ? `${topSector.value.toLocaleString('vi-VN')} tấn` : 'Thử chọn tháng 6/2026'} />
      </section>

      <section className="admin-visual-grid" aria-label="Phân tích điều hành">
        <div className="admin-visual-grid__map">
          <VietnamProvinceMap
            selectedProvinceCode={filters.provinceCode}
            metric={mapMetric}
            layerVisible={mapLayerVisible}
            onMetricChange={setMapMetric}
            onLayerVisibilityChange={setMapLayerVisible}
            onProvinceSelect={(province) => setFilters((current) => ({ ...current, provinceCode: province.provinceCode }))}
          />
        </div>

        <div className="admin-visual-grid__provinces">
          <HorizontalBarChart
            eyebrow="Xếp hạng không gian"
            title="Top tỉnh theo PM2.5"
            description="Xếp hạng PM2.5 trung bình theo kỳ đang chọn. Chọn một thanh để lọc toàn bộ dashboard theo tỉnh."
            points={provinceRanking.slice(0, 5)}
            unit="µg/m³"
            fileName={`top-tinh-pm25-${currentYear}`}
            selectedId={filters.provinceCode === 'all' ? undefined : filters.provinceCode}
            onSelect={(point) => setFilters((current) => ({ ...current, provinceCode: point.id as ProvinceCode }))}
          />
        </div>

        <div className="admin-visual-grid__trend">
          <TrendChart
            title={`${metric.label} dài hạn · ${scopeLabel}`}
            description="Chuỗi thời gian theo tháng, tự động cập nhật theo tỉnh, chất ô nhiễm, năm, tháng và khoảng ngày đang chọn."
            points={chartPoints}
            metricLabel={metric.label}
            unit={metric.unit}
            fileName={`xu-huong-dai-han-${filters.pollutant}-${filters.provinceCode}`}
          />
        </div>

        <div className="admin-visual-grid__sectors">
          <HorizontalBarChart
            eyebrow="Cơ cấu nguồn thải"
            title="Top ngành phát thải"
            description="Tổng phát thải PM2.5 theo ngành trong phạm vi hiện tại. Chọn một thanh để lọc theo ngành."
            points={sectorRanking.slice(0, 5)}
            unit="tấn"
            fileName={`top-nganh-phat-thai-${currentYear}`}
            selectedId={filters.sector === 'all' ? undefined : filters.sector}
            onSelect={(point) => setFilters((current) => ({ ...current, sector: current.sector === point.id ? 'all' : point.id }))}
          />
        </div>
      </section>

      <PriorityAreasTable
        areas={priorityAreaRows}
        selectedProvinceCode={filters.provinceCode}
        onProvinceSelect={(provinceCode) => setFilters((current) => ({ ...current, provinceCode }))}
      />

      <footer className="admin-disclaimer">
        <strong>Lưu ý dữ liệu:</strong> Các chỉ số trên trang là dữ liệu minh họa phục vụ prototype, không dùng để đưa ra kết luận chuyên môn hoặc quyết định quản lý thực tế.
      </footer>
    </main>
  )
}
