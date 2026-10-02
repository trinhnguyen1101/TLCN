import { useState } from 'react'
import type { DashboardData, DashboardFiltersValue } from '../../types/dashboard'
import { matchesPeriod, mean } from '../../services/dashboardSelectors'
import { ComparisonPanel, type ComparisonValue } from './ComparisonPanel'

export function DashboardComparison({ data, filters, years, unit, loading }: { data: DashboardData | null; filters: DashboardFiltersValue; years: number[]; unit: string; loading: boolean }) {
  const [selection, setSelection] = useState<Partial<ComparisonValue>>({})
  const value: ComparisonValue = { dimension: 'province', provinceCode: data?.provinceSnapshots[1]?.provinceCode ?? data?.provinceSnapshots[0]?.provinceCode ?? '', year: years[1] ?? years[0] ?? 0, ...selection }
  const name = (code: string) => code === 'all' ? 'Toàn quốc' : data?.provinceSnapshots.find((province) => province.provinceCode === code)?.provinceName ?? code
  const currentYear = filters.year === 'all' ? years[0] : filters.year
  const currentFilters = value.dimension === 'province' ? filters : { ...filters, year: currentYear ?? 'all' as const }
  const otherFilters = value.dimension === 'province' ? { ...filters, provinceCode: value.provinceCode } : {
    ...filters, year: value.year,
    startDate: filters.startDate ? `${value.year}${filters.startDate.slice(4)}` : '',
    endDate: filters.endDate ? `${value.year}${filters.endDate.slice(4)}` : '',
  }
  const average = (scope: DashboardFiltersValue) => mean((data?.dashboardTrendRecords ?? []).filter((row) => matchesPeriod(row, scope)).map((row) => row[filters.pollutant]))
  return <ComparisonPanel years={years} dataReady={Boolean(data)} loading={loading} value={value} provinces={data?.provinceSnapshots ?? []} currentLabel={value.dimension === 'province' ? name(filters.provinceCode) : String(currentYear ?? '—')} comparisonLabel={value.dimension === 'province' ? name(value.provinceCode) : String(value.year)} currentValue={average(currentFilters)} comparisonValue={average(otherFilters)} unit={unit} onChange={setSelection} />
}
