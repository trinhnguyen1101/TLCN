import { sectorLabel } from '../../../utils/labels'
import type { AdminDashboardData, DashboardFiltersValue, PriorityArea } from '../types'
import { buildMonitoringView, comparisonYear, isFullYearPeriod, isNumber, matchesEmissionPeriod, matchesPeriod, mean, metricOptions, shiftPeriodYear } from './dashboardSelectors'
import { periodYears } from './temporal'

function trendFromChange(change: number | null): PriorityArea['trend'] {
  if (change === null) return null
  if (change >= 8) return 'up'
  if (change > 2) return 'slight-up'
  if (change <= -2) return 'down'
  return 'steady'
}

export function buildAdminDashboardView(data: AdminDashboardData | null, filters: DashboardFiltersValue) {
  const trends = data?.dashboardTrendRecords ?? []
  const pollutantOptions = metricOptions(data)
  const availableMetrics = pollutantOptions.map((option) => option.value)
  const selectedPollutant = availableMetrics.includes(filters.pollutant) ? filters.pollutant : availableMetrics[0] ?? 'pm25'
  const monitoring = buildMonitoringView(data, { ...filters, pollutant: selectedPollutant })
  const years = periodYears(data?.metadata, [...new Set(trends.map((record) => Number(record.date.slice(0, 4))).filter(Number.isFinite))].sort((a, b) => b - a), filters.resolution)
  const currentRecords = monitoring.records
  const baseYear = comparisonYear(filters)
  const currentYear = baseYear ?? undefined
  const previousFilters = baseYear === null ? null : shiftPeriodYear(filters, -1)
  const previousRecords = previousFilters ? (data?.comparisonTrendRecords ?? trends).filter((record) => matchesPeriod(record, previousFilters, true, data?.metadata?.temporalAggregation)) : []
  const currentPm25 = mean(currentRecords.map((record) => record.pm25))
  const previousPm25 = mean(previousRecords.map((record) => record.pm25))
  const yoy = currentPm25 !== null && previousPm25 !== null && previousPm25 !== 0
    ? (currentPm25 - previousPm25) / previousPm25 * 100 : null
  const filteredEmissions = (data?.emissionRecords ?? []).filter((record) => matchesEmissionPeriod(record, filters))
  const sectorGroups = new Map<string, number>()
  filteredEmissions.forEach((record) => {
    if (isNumber(record.emissionTonnes)) sectorGroups.set(record.sector, (sectorGroups.get(record.sector) ?? 0) + record.emissionTonnes)
  })
  const sectorRanking = [...sectorGroups].map(([id, value]) => ({ id, label: sectorLabel(id), value: Math.round(value) })).sort((a, b) => b.value - a.value)
  const totalEmissions = filteredEmissions.length ? filteredEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0) : null
  const fullYear = isFullYearPeriod(filters)
  const priorityAreaRows = (data?.priorityAreas ?? [])
    .filter((area) => filters.provinceCode === 'all' || area.provinceCode === filters.provinceCode)
    .map((area) => {
      const areaCurrent = currentRecords.filter((record) => record.provinceCode === area.provinceCode)
      const areaPrevious = previousRecords.filter((record) => record.provinceCode === area.provinceCode)
      const pm25Average = mean(areaCurrent.map((record) => record.pm25))
      const previousAverage = mean(areaPrevious.map((record) => record.pm25))
      const change = pm25Average !== null && previousAverage !== null && previousAverage !== 0 ? (pm25Average - previousAverage) / previousAverage * 100 : null
      const areaEmissions = filteredEmissions.filter((record) => record.provinceCode === area.provinceCode)
      const emissionsTotal = areaEmissions.length ? areaEmissions.reduce((sum, record) => sum + (isNumber(record.emissionTonnes) ? record.emissionTonnes : 0), 0) : null
      const sectors = new Map<string, number>()
      areaEmissions.forEach((record) => {
        if (isNumber(record.emissionTonnes)) sectors.set(record.sector, (sectors.get(record.sector) ?? 0) + record.emissionTonnes)
      })
      const mainEmissionSector = [...sectors].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null
      // Annual totals cannot be divided into months or days without dated observations.
      const exceedanceDays = fullYear ? data?.annualProvinceSummaries.find((summary) => summary.provinceCode === area.provinceCode && summary.year === filters.year)?.exceedanceDays ?? null : null
      return { ...area, pm25Average, yearOverYearPercent: change, exceedanceDays, totalEmissions: emissionsTotal, mainEmissionSector, trend: trendFromChange(change) }
    })
  return {
    monitoring, availableMetrics, pollutantOptions, years, currentYear, selectedPollutant,
    metric: monitoring.metric, scopeLabel: monitoring.scopeLabel, chartPoints: monitoring.chartPoints,
    sectorRanking, totalEmissions, currentAqi: monitoring.aqi, yoy, comparisonYear: baseYear, priorityAreaRows, topSector: sectorRanking[0],
  }
}
export type AdminDashboardView = ReturnType<typeof buildAdminDashboardView>
