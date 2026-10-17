import { useState } from 'react'
import type { DashboardData, DashboardFiltersValue } from '../types'
import { matchesPeriod, mean } from '../model/dashboardSelectors'
import { comparisonFilters, temporalQuery } from '../model/temporal'
import { loadDashboardData } from '../api/dashboardApi'
import { useTemporalData } from '../hooks/useTemporalData'
import type { DashboardLoader } from '../api/dashboardTransport'
import { ComparisonPanel, type ComparisonValue } from './ComparisonPanel'
import { Button } from '../../../components/ui/Button'

interface DashboardComparisonProps {
  data: DashboardData | null
  filters: DashboardFiltersValue
  years: number[]
  unit: string
  loading: boolean
  load?: DashboardLoader
}

export function DashboardComparison({ data, filters, years, unit, loading, load = loadDashboardData }: DashboardComparisonProps) {
  const [selection, setSelection] = useState<Partial<ComparisonValue>>({})
  const value: ComparisonValue = { dimension: 'province', provinceCode: data?.provinceSnapshots[1]?.provinceCode ?? data?.provinceSnapshots[0]?.provinceCode ?? '', year: years[1] ?? years[0] ?? 0, ...selection }
  const name = (code: string) => code === 'all' ? 'Toàn quốc' : data?.provinceSnapshots.find((province) => province.provinceCode === code)?.provinceName ?? code
  const currentYear = filters.year === 'all' ? Number(filters.endDate.slice(0, 4)) || years[0] : filters.year
  const currentFilters = value.dimension === 'year' && filters.resolution === 'monthly' && currentYear !== undefined
    && filters.startDate.slice(0, 4) !== filters.endDate.slice(0, 4)
    ? { ...filters, year: currentYear, startDate: `${currentYear}-01-01`, endDate: `${currentYear}-12-31` } : filters
  const otherFilters = value.dimension === 'province' ? { ...filters, provinceCode: value.provinceCode } : comparisonFilters(currentFilters, value.year)
  const yearComparison = value.dimension === 'year' && Boolean(data)
  const sameYear = value.year === currentYear
  const previousYear = value.year === Number(data?.metadata?.queryEnd?.slice(0, 4)) - 1 && data?.comparisonTrendRecords !== undefined
  const existingReference = filters.resolution === 'monthly' && data?.dashboardTrendRecords.some((row) => matchesPeriod(row, otherFilters))
  const sourceStart = filters.resolution === 'monthly' ? data?.metadata?.start : data?.metadata?.observationStart
  const sourceEnd = filters.resolution === 'monthly' ? data?.metadata?.end : data?.metadata?.observationEnd
  const outsideSource = Boolean(sourceStart && otherFilters.endDate < sourceStart.slice(0, 16)
    || sourceEnd && otherFilters.startDate > sourceEnd.slice(0, 16))
  const reference = useTemporalData(load, temporalQuery(otherFilters), value.year, yearComparison && !sameYear && !previousYear && !existingReference && !outsideSource, false)
  const generationChanged = reference.data && reference.data.metadata?.generation !== data?.metadata?.generation
  const error = reference.error ?? (generationChanged ? 'Bộ dữ liệu đã thay đổi. Hãy tải lại để so sánh cùng nguồn.' : null)
  const referenceRecords = !yearComparison || sameYear || existingReference ? data?.dashboardTrendRecords ?? []
    : outsideSource ? [] : previousYear ? data?.comparisonTrendRecords ?? [] : !reference.loading && !error ? reference.data?.dashboardTrendRecords ?? [] : []
  const average = (rows: DashboardData['dashboardTrendRecords'], scope: DashboardFiltersValue) => mean(rows.filter((row) => matchesPeriod(row, scope)).map((row) => row[filters.pollutant]))
  return <div>
    {error && <div role="alert" className="mb-3 flex items-center justify-between gap-3 text-xs text-danger"><span>{error}</span><Button onClick={reference.retry}>Thử lại</Button></div>}
    <ComparisonPanel years={years} dataReady={Boolean(data) && !reference.loading && !error} loading={loading || reference.loading} value={value} provinces={data?.provinceSnapshots ?? []} currentLabel={value.dimension === 'province' ? name(filters.provinceCode) : String(currentYear ?? '—')} comparisonLabel={value.dimension === 'province' ? name(value.provinceCode) : String(value.year)} currentValue={average(data?.dashboardTrendRecords ?? [], currentFilters)} comparisonValue={average(referenceRecords, otherFilters)} unit={unit} onChange={setSelection} />
  </div>
}
