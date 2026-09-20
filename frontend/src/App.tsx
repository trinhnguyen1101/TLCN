import { useMemo, useState } from 'react'
import { ComparisonPanel, type ComparisonValue } from './components/dashboard/ComparisonPanel'
import { DashboardBreadcrumb } from './components/dashboard/DashboardBreadcrumb'
import { DashboardFilters } from './components/dashboard/DashboardFilters'
import { DataState } from './components/dashboard/DataState'
import { TrendChart } from './features/analytics/TrendChart'
import { VietnamProvinceMap, type MapMetric } from './features/geography/VietnamProvinceMap'
import { dashboardTrendRecords, emissionRecords, emissionSectors, provinceSnapshots } from './services/mockDashboardData'
import type { ChartPoint, DashboardFiltersValue, DashboardTrendRecord, ProvinceCode } from './types/dashboard'
import './App.css'

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

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p>Air Quality Dashboard · Demo</p>
          <h1>Phân tích chất lượng không khí</h1>
          <span>Bộ tính năng chung dùng lại cho các dashboard User và Admin.</span>
        </div>
        <span className="demo-badge">Dữ liệu minh họa</span>
      </header>

      <DashboardFilters value={filters} provinces={provinceSnapshots} sectors={emissionSectors} onChange={setFilters} onReset={() => setFilters(DEFAULT_FILTERS)} />
      <DashboardBreadcrumb items={breadcrumbItems} />

      <section className="summary-grid" aria-label="Tóm tắt bộ lọc">
        <article><span>Khu vực</span><strong>{scopeLabel}</strong></article>
        <article><span>{metric.label} trung bình</span><strong>{mean(filteredRecords.map((record) => record[filters.pollutant]))?.toFixed(1) ?? 'Chưa có dữ liệu'} {filteredRecords.length ? metric.unit : ''}</strong></article>
        <article><span>Tổng phát thải</span><strong>{filteredEmissions.length ? `${totalEmissions.toLocaleString('vi-VN')} tấn` : 'Chưa có dữ liệu'}</strong></article>
      </section>

      <div className="dashboard-grid">
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
          description="Biểu đồ tự động cập nhật theo tỉnh, chất ô nhiễm, năm, tháng và khoảng ngày đang chọn. Rê chuột hoặc dùng phím Tab trên từng điểm để xem tooltip."
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

        <section className="emission-card" aria-labelledby="emission-title">
          <div>
            <p className="eyebrow">Bộ lọc ngành</p>
            <h2 id="emission-title">Dữ liệu phát thải phù hợp</h2>
          </div>
          <DataState isEmpty={filteredEmissions.length === 0} emptyMessage="Dữ liệu phát thải demo hiện chỉ có cho tháng 6/2026.">
            <div className="emission-list">
              {filteredEmissions.map((record) => (
                <div key={`${record.provinceCode}-${record.sector}`}>
                  <span>{record.provinceName} · {record.sector}</span>
                  <strong>{record.emissionTonnes.toLocaleString('vi-VN')} tấn</strong>
                </div>
              ))}
            </div>
          </DataState>
        </section>
      </div>
    </main>
  )
}

export default App
