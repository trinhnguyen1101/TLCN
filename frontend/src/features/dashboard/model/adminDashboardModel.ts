import { sectorLabel } from '../../../utils/labels'
import { shiftDateYear } from '../../../utils/dates'
import type { AdminDashboardData, DashboardFiltersValue, DashboardTrendRecord, PriorityArea } from '../types'
import { buildMonitoringView, comparisonYear, isFullYearPeriod, isNumber, matchesEmissionPeriod, matchesPeriod, weightedMetricMean, metricOptions, shiftPeriodYear } from './dashboardSelectors'
import { periodYears } from './temporal'

function trendFromChange(change: number | null): PriorityArea['trend'] {
  if (change === null) return null
  if (change >= 8) return 'up'
  if (change > 2) return 'slight-up'
  if (change <= -2) return 'down'
  return 'steady'
}

/** Compare only province/calendar slots with valid PM2.5 in both years. */
function matchedYoY(current: DashboardTrendRecord[], previous: DashboardTrendRecord[], resolution: DashboardFiltersValue['resolution']) {
  const width = resolution === 'monthly' ? 7 : resolution === 'daily' ? 10 : 13
  const key = (row: DashboardTrendRecord, date = row.date) => `${row.provinceCode}|${date.slice(0, width)}`
  const previousKeys = new Set(previous.filter(row => isNumber(row.pm25)).map(row => key(row)))
  const currentPairs = current.filter(row => {
    if (!isNumber(row.pm25)) return false
    const shifted = shiftDateYear(row.date, -1)
    // Feb29 has no daily/hourly counterpart in a non-leap year. Do not reuse
    // Feb28 twice; period endpoints can still clamp through shiftPeriodYear.
    if (resolution !== 'monthly' && shifted.slice(5, 10) !== row.date.slice(5, 10)) return false
    return previousKeys.has(key(row, shifted))
  })
  const commonKeys = new Set(currentPairs.map(row => key(row, shiftDateYear(row.date, -1))))
  const previousPairs = previous.filter(row => isNumber(row.pm25) && commonKeys.has(key(row)))
  const value = weightedMetricMean(currentPairs, 'pm25')
  const baseline = weightedMetricMean(previousPairs, 'pm25')
  return value !== null && baseline !== null && baseline !== 0 ? (value - baseline) / baseline * 100 : null
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
  const yoy = matchedYoY(currentRecords, previousRecords, filters.resolution)
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
      const pm25Average = weightedMetricMean(areaCurrent, 'pm25')
      const change = matchedYoY(areaCurrent, areaPrevious, filters.resolution)
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
