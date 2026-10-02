import type { AdminDashboardData, DashboardFiltersValue, Pollutant } from '../../types/dashboard'
import type { AdminDashboardView } from '../../services/adminDashboardModel'
import { AnalyticsTabs } from '../../components/dashboard/AnalyticsTabs'
import { DashboardComparison } from '../../components/dashboard/DashboardComparison'
import { DataQualityPanel } from '../../components/dashboard/DataQualityPanel'
import { EmissionTable } from '../../components/dashboard/EmissionTable'
import { PollutantMetrics } from '../../components/dashboard/PollutantMetrics'
import { PriorityAreasTable } from '../../components/dashboard/PriorityAreasTable'
import { TrendChart } from '../../features/analytics/TrendChart'
import { HorizontalBarChart } from '../../features/analytics/HorizontalBarChart'

const TABS = [{ id: 'overview', label: 'Tổng quan' }, { id: 'pollutants', label: 'Chất ô nhiễm' }, { id: 'provinces', label: 'Tỉnh / thành' }, { id: 'emissions', label: 'Phát thải' }, { id: 'qcvn', label: 'QCVN' }, { id: 'quality', label: 'Chất lượng dữ liệu' }]
interface Props {
  data: AdminDashboardData | null
  filters: DashboardFiltersValue
  view: AdminDashboardView
  loading: boolean
  tab: string
  onTabChange: (tab: string) => void
  onProvinceSelect: (code: string) => void
  onPollutantSelect: (pollutant: Pollutant) => void
  onSectorSelect: (sector: string) => void
}
export function AdminAnalytics({ data, filters, view, loading, tab, onTabChange, onProvinceSelect, onPollutantSelect, onSectorSelect }: Props) {
  const trend = <TrendChart dataReady={Boolean(data)} loading={loading} compact title={`${view.metric.label} · ${view.scopeLabel}`} description="Giá trị trung bình theo tháng trong kỳ đang chọn." points={view.chartPoints} metricLabel={view.metric.label} unit={view.metric.unit} fileName={`phan-tich-${view.selectedPollutant}-${filters.provinceCode}`} />
  const fullYear = filters.year !== 'all' && filters.month === 'all' && !filters.startDate && !filters.endDate
  const thresholdRows = fullYear ? (data?.annualProvinceSummaries ?? []).filter((row) => row.year === filters.year && row.exceedanceDays !== null && (filters.provinceCode === 'all' || row.provinceCode === filters.provinceCode)) : []
  return <AnalyticsTabs tabs={TABS} value={tab} onChange={onTabChange}>
    {tab === 'overview' && <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1"><DashboardComparison data={data} filters={filters} years={view.years} unit={view.metric.unit} loading={loading} /><section className="rounded-card border border-border bg-surface p-5"><h2 className="text-sm font-semibold text-heading">Tóm tắt kỳ báo cáo</h2><dl className="mt-4 grid grid-cols-2 gap-4 text-xs text-muted"><div><dt>Bản ghi thời gian</dt><dd className="mt-1 text-xl text-heading">{data ? view.monitoring.records.length : '—'}</dd></div><div><dt>Tỉnh có {view.metric.label}</dt><dd className="mt-1 text-xl text-heading">{data ? view.monitoring.reportingProvinces : '—'}</dd></div><div><dt>Tổng phát thải</dt><dd className="mt-1 text-lg text-heading">{view.totalEmissions === null ? '—' : `${Math.round(view.totalEmissions).toLocaleString('vi-VN')} tấn`}</dd></div><div><dt>Ngành phát thải lớn nhất</dt><dd className="mt-1 text-lg text-heading">{view.topSector?.label ?? '—'}</dd></div></dl><p className="mt-4 text-xs leading-relaxed text-muted">{data?.metadata?.note ?? 'Chỉ số được tổng hợp từ dữ liệu nguồn trong phạm vi bộ lọc.'}</p></section></div>}
    {tab === 'pollutants' && <div className="grid grid-cols-[minmax(240px,1fr)_minmax(0,2fr)] gap-4 max-md:grid-cols-1"><div className="max-h-[330px] overflow-y-auto"><PollutantMetrics metrics={view.monitoring.metrics} metadata={data?.metadata?.metrics} pollutants={view.availableMetrics} selected={view.selectedPollutant} onSelect={onPollutantSelect} /></div>{trend}</div>}
    {tab === 'provinces' && <PriorityAreasTable areas={view.priorityAreaRows} selectedProvinceCode={filters.provinceCode} onProvinceSelect={onProvinceSelect} />}
    {tab === 'emissions' && <div className="grid grid-cols-2 gap-4 max-md:grid-cols-1"><HorizontalBarChart eyebrow="Cơ cấu nguồn thải" title="Ngành phát thải" description="Tổng lượng phát thải trong phạm vi bộ lọc." points={view.sectorRanking} unit="tấn" fileName="nganh-phat-thai" selectedId={filters.sector} onSelect={(point) => onSectorSelect(point.id)} /><EmissionTable data={data} filters={filters} loading={loading} /></div>}
    {tab === 'qcvn' && <section className="rounded-card border border-border bg-surface p-5"><h2 className="text-sm font-semibold text-heading">Theo dõi ngưỡng từ nguồn dữ liệu</h2><p className="mt-2 text-xs leading-relaxed text-muted">Nguồn chưa cung cấp ngưỡng, thời gian lấy trung bình và phiên bản QCVN để xác nhận tuân thủ. Số ngày vượt ngưỡng chỉ hiển thị theo tổng hợp cả năm do nguồn cung cấp.</p>{thresholdRows.length > 0 ? <div className="mt-4 max-h-[300px] overflow-auto"><table className="w-full text-left text-xs text-secondary"><thead><tr><th scope="col" className="p-2">Tỉnh / thành</th><th scope="col" className="p-2">Năm</th><th scope="col" className="p-2">Ngày vượt ngưỡng nguồn</th></tr></thead><tbody>{thresholdRows.map((row) => <tr key={row.provinceCode}><td className="border-t border-border p-2">{row.provinceName}</td><td className="border-t border-border p-2">{row.year}</td><td className="border-t border-border p-2">{row.exceedanceDays}</td></tr>)}</tbody></table></div> : <p className="mt-4 text-sm text-muted">{fullYear ? 'Chưa có số ngày vượt ngưỡng cho kỳ này.' : 'Chọn một năm, tất cả tháng và bỏ khoảng ngày để xem số liệu cả năm.'}</p>}</section>}
    {tab === 'quality' && <DataQualityPanel data={data} filters={filters} />}
  </AnalyticsTabs>
}
