import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

// Exercise the actual TypeScript selectors without adding a runtime/test library.
function sourceModule(path) {
  const url = new URL(path, import.meta.url)
  let source = ts.transpileModule(readFileSync(url, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  source = source.replace(/from (['"])(\.[^'"]+)\1/g, (_, quote, dependency) => {
    const target = new URL(`${dependency}.ts`, url)
    return `from ${quote}${sourceModule(target)}${quote}`
  })
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
}
const datesUrl = sourceModule('../src/utils/dates.ts')
const labelsUrl = sourceModule('../src/utils/labels.ts')
const selectorsUrl = sourceModule('../src/features/dashboard/model/dashboardSelectors.ts')
const { buildMonitoringView, DEFAULT_FILTERS: sourceDefaults, matchesPeriod, matchesEmissionPeriod, mean, periodLabel, shiftPeriodYear, updateDashboardFilter } = await import(selectorsUrl)
const { parseVietnameseDate, formatDate } = await import(datesUrl)
const { sectorLabel, sourceLabel, aggregationLabel } = await import(labelsUrl)
const { buildAdminDashboardView } = await import(sourceModule('../src/features/dashboard/model/adminDashboardModel.ts'))

const DEFAULT_FILTERS = { ...sourceDefaults, resolution: 'monthly' }

const snapshot = (code, value) => ({ provinceCode: code, provinceName: code, aqi: 200, status: 'Xấu', pm25: value, pm10: value * 2 })
const record = (code, date, value) => ({ provinceCode: code, date, pm25: value, pm10: value * 2, no2: null, so2: null, co: null, o3: null })
const data = {
  provinceSnapshots: [snapshot('01', 90), snapshot('79', 50)],
  dashboardTrendRecords: [record('01', '2025-01-15', 10), record('01', '2026-01-15', 20), record('79', '2026-01-15', 40), record('01', '2026-02-15', 60)],
  emissionRecords: [{ provinceCode: '01', provinceName: '01', year: 2025, month: 1, sector: 'Power', emissionTonnes: 10 }, { provinceCode: '01', provinceName: '01', year: 2026, month: 1, sector: 'Power', emissionTonnes: 20 }],
  emissionSectors: ['Power'],
  priorityAreas: [{ provinceCode: '01', provinceName: '01', pm25Average: 999, yearOverYearPercent: 999, exceedanceDays: 999, totalEmissions: 999, mainEmissionSector: 'Old', trend: 'up' }],
  annualProvinceSummaries: [{ provinceCode: '01', provinceName: '01', year: 2026, pm25Average: 30, aqiAverage: null, yearOverYearPercent: null, exceedanceDays: 42 }],
}

test('a province selection scopes metrics and chart but preserves national map context', () => {
  const view = buildMonitoringView(data, { ...DEFAULT_FILTERS, provinceCode: '01', year: 2026, month: 1 })
  assert.equal(view.metrics.pm25, 20)
  assert.deepEqual(view.chartPoints, [{ label: '01/2026', timestamp: '2026-01', value: 20 }])
  assert.equal(view.snapshots.find((p) => p.provinceCode === '79').pm25, 40)
  assert.equal(view.reportingProvinces, 1)
})
test('historical data never inherits a current AQI snapshot or unavailable gas', () => {
  const view = buildMonitoringView(data, { ...DEFAULT_FILTERS, year: 2026 })
  assert.equal(view.aqi, null)
  assert.equal(view.metrics.co, null)
  assert.equal(buildMonitoringView(data, DEFAULT_FILTERS, true).aqi, 200)
})
test('pollutant selection updates ranking, unit and series consistently', () => {
  const view = buildAdminDashboardView(data, { ...DEFAULT_FILTERS, pollutant: 'pm10', year: 2026, month: 1 })
  assert.equal(view.monitoring.metrics.pm10, 60)
  assert.equal(view.monitoring.ranking[0].id, '79')
  assert.equal(view.monitoring.ranking[0].value, 80)
  assert.equal(view.chartPoints[0].value, 60)
})
test('all-years totals and concentration means use the same period as the trend', () => {
  const view = buildAdminDashboardView(data, DEFAULT_FILTERS)
  assert.equal(view.monitoring.metrics.pm25, 35) // equal weight to each province's period mean
  assert.equal(view.totalEmissions, 30)
  assert.equal(view.yoy, null)
})
test('custom dates constrain all monthly concentration views and empty periods remain empty', () => {
  const view = buildAdminDashboardView(data, { ...DEFAULT_FILTERS, startDate: '2026-02-01', endDate: '2026-02-28' })
  assert.equal(view.monitoring.metrics.pm25, 60)
  assert.equal(view.chartPoints.length, 1)
  assert.equal(view.totalEmissions, null)
  const empty = buildAdminDashboardView(data, { ...DEFAULT_FILTERS, year: 2030 })
  assert.equal(empty.monitoring.metrics.pm25, null)
  assert.equal(empty.priorityAreaRows[0].pm25Average, null)
  assert.equal(empty.priorityAreaRows[0].totalEmissions, null)
  assert.equal(empty.priorityAreaRows[0].yearOverYearPercent, null)
})
test('annual exceedance counts are never estimated for a partial year', () => {
  assert.equal(buildAdminDashboardView(data, { ...DEFAULT_FILTERS, year: 2026 }).priorityAreaRows[0].exceedanceDays, 42)
  assert.equal(buildAdminDashboardView(data, { ...DEFAULT_FILTERS, year: 2026, month: 1 }).priorityAreaRows[0].exceedanceDays, null)
})
test('YoY uses the same province and month in the previous year', () => {
  assert.equal(buildAdminDashboardView(data, { ...DEFAULT_FILTERS, year: 2026, month: 1, provinceCode: '01' }).yoy, 100)
})
test('missing/non-finite values cannot become zero readings', () => {
  assert.equal(mean([null, undefined, NaN, Infinity]), null)
  assert.equal(mean([0, null]), 0)
  assert.equal(buildAdminDashboardView(null, DEFAULT_FILTERS).currentAqi, null)
})

test('Vietnamese dates parse strictly, reject invalid calendar dates and display dd/mm/yyyy', () => {
  assert.equal(parseVietnameseDate('29/02/2024'), '2024-02-29')
  for (const value of ['29/02/2025', '31/04/2026', '12/13/2026', '03/10/0000', '1/2/2026', '2026-10-03']) {
    assert.equal(parseVietnameseDate(value), null, value)
  }
  assert.equal(formatDate('2026-10-03T00:00:00Z'), '03/10/2026')
  assert.equal(periodLabel({ ...DEFAULT_FILTERS, startDate: '2025-12-20', endDate: '2026-01-10' }), '20/12/2025 → 10/01/2026 UTC')
})

test('entering a custom range clears year/month and selecting year/month clears custom dates', () => {
  const start = updateDashboardFilter({ ...DEFAULT_FILTERS, year: 2026, month: 6 }, 'startDate', '2025-12-20')
  assert.equal(start.year, 'all')
  assert.equal(start.month, 'all')
  const range = updateDashboardFilter(start, 'endDate', '2026-01-10')
  for (const [key, value] of [['year', 2025], ['month', 2]]) {
    const changed = updateDashboardFilter(range, key, value)
    assert.equal(changed.startDate, '')
    assert.equal(changed.endDate, '')
  }
})

test('daily ranges override stale year/month selections and include both boundary days', () => {
  const filters = { ...DEFAULT_FILTERS, year: 2030, month: 8, startDate: '2026-01-15', endDate: '2026-02-15' }
  const view = buildAdminDashboardView(data, filters)
  assert.equal(view.monitoring.records.length, 3)
  assert.deepEqual(view.chartPoints, [{ label: '01/2026', timestamp: '2026-01', value: 30 }, { label: '02/2026', timestamp: '2026-02', value: 60 }])
  assert.equal(view.monitoring.snapshots[0].pm25, 40)
  assert.equal(view.monitoring.metrics.pm25, 40)
  assert.equal(view.totalEmissions, 20)
  assert.equal(view.priorityAreaRows[0].pm25Average, 40)
  assert.equal(view.priorityAreaRows[0].exceedanceDays, null)
  assert.equal(matchesPeriod(record('01', '2026-01-14', 1), { ...filters, resolution: 'daily' }), false)
  assert.equal(matchesPeriod(record('01', '2026-02-16', 1), { ...filters, resolution: 'daily' }), false)
})

test('monthly source includes overlapping boundary months independently of timestamp day', () => {
  const monthly = { ...data, metadata: { temporalAggregation: 'monthly_mean', metrics: {} },
    dashboardTrendRecords: [record('01', '2025-12-01', 10), record('01', '2026-01-01', 30), record('01', '2026-02-01', 100)] }
  const filters = { ...DEFAULT_FILTERS, year: 2026, month: 2, startDate: '2025-12-20', endDate: '2026-01-10' }
  const admin = buildAdminDashboardView(monthly, filters)
  const user = buildMonitoringView(monthly, filters)
  assert.deepEqual(admin.chartPoints, [{ label: '12/2025', timestamp: '2025-12', value: 10 }, { label: '01/2026', timestamp: '2026-01', value: 30 }])
  assert.equal(admin.monitoring.metrics.pm25, 20)
  assert.equal(admin.monitoring.snapshots[0].pm25, 20)
  assert.equal(admin.priorityAreaRows[0].pm25Average, 20)
  assert.equal(admin.totalEmissions, 20)
  assert.deepEqual(user.chartPoints, admin.chartPoints)
  assert.deepEqual(user.snapshots, admin.monitoring.snapshots)
  assert.equal(monthly.dashboardTrendRecords.filter((row) => matchesPeriod(row, filters, true, monthly.metadata.temporalAggregation)).length, 2)
  // A daily source must not include dates outside the actual range.
  assert.equal(matchesPeriod(record('01', '2025-12-01', 10), { ...filters, resolution: 'daily' }), false)
})

test('monthly ranges cover same-month, open-ended and empty periods; reversed ranges stay empty', () => {
  const monthly = { ...data, metadata: { temporalAggregation: 'monthly_mean', metrics: {} } }
  const sameMonth = { ...DEFAULT_FILTERS, startDate: '2026-01-20', endDate: '2026-01-21' }
  assert.equal(buildAdminDashboardView(monthly, sameMonth).monitoring.records.length, 2)
  assert.equal(buildAdminDashboardView(monthly, sameMonth).totalEmissions, 20)
  assert.equal(buildAdminDashboardView(monthly, { ...DEFAULT_FILTERS, startDate: '2026-02-20' }).monitoring.metrics.pm25, 60)
  assert.equal(buildAdminDashboardView(monthly, { ...DEFAULT_FILTERS, endDate: '2025-01-01' }).monitoring.metrics.pm25, 10)
  for (const filters of [
    { ...DEFAULT_FILTERS, startDate: '2030-01-01', endDate: '2030-01-31' },
    { ...DEFAULT_FILTERS, startDate: '2026-02-20', endDate: '2026-01-01' },
    { ...DEFAULT_FILTERS, startDate: '2026-02-30' },
  ]) {
    const view = buildAdminDashboardView(monthly, filters)
    assert.equal(view.monitoring.metrics.pm25, null)
    assert.deepEqual(view.chartPoints, [])
    assert.equal(view.totalEmissions, null)
    assert.equal(view.priorityAreaRows[0].pm25Average, null)
    assert.equal(monthly.emissionRecords.some((row) => matchesEmissionPeriod(row, filters)), false)
  }
})

test('same-period comparisons shift each date by one year and clamp leap days', () => {
  const range = { ...DEFAULT_FILTERS, startDate: '2025-12-20', endDate: '2026-01-10' }
  assert.deepEqual(shiftPeriodYear(range, -1), { ...range, startDate: '2024-12-20', endDate: '2025-01-10' })
  assert.equal(shiftPeriodYear({ ...DEFAULT_FILTERS, endDate: '2024-02-29' }, -1).endDate, '2023-02-28')
  const monthly = { ...data, metadata: { temporalAggregation: 'monthly_mean', metrics: {} },
    dashboardTrendRecords: [record('01', '2024-12-01', 10), record('01', '2025-01-01', 20), record('01', '2025-12-01', 20), record('01', '2026-01-01', 40)] }
  assert.equal(buildAdminDashboardView(monthly, range).yoy, 100)
})

test('source metadata and sector names have Vietnamese display labels', () => {
  assert.equal(sectorLabel('Power'), 'Sản xuất điện')
  assert.equal(sectorLabel('Manufacturing'), 'Sản xuất công nghiệp')
  assert.equal(sourceLabel('CAMS EAC4 sample'), 'Dữ liệu mẫu CAMS EAC4')
  assert.equal(aggregationLabel('monthly_mean'), 'Trung bình tháng')
  const view = buildAdminDashboardView(data, DEFAULT_FILTERS)
  assert.equal(view.sectorRanking[0].label, 'Sản xuất điện')
  assert.equal(view.sectorRanking[0].id, 'Power')
})

test('date filtering retains three-hour observations and inclusive UTC day boundaries', () => {
  const filters = { ...sourceDefaults, startDate: '2026-01-15', endDate: '2026-01-15' }
  assert.equal(matchesPeriod(record('01', '2026-01-15T00:00:00Z', 1), filters), true)
  assert.equal(matchesPeriod(record('01', '2026-01-15T21:00:00Z', 1), filters), true)
  assert.equal(matchesPeriod(record('01', '2026-01-16T00:00:00Z', 1), filters), false)
  const instant = { ...filters, startDate: '2026-01-15T03:00', endDate: '2026-01-15T06:00' }
  assert.equal(matchesPeriod(record('01', '2026-01-15T03:00:00Z', 1), instant), true)
  assert.equal(matchesPeriod(record('01', '2026-01-15T09:00:00Z', 1), instant), false)
  assert.equal(shiftPeriodYear({ ...instant, startDate: '2024-02-29T03:00' }, -1).startDate, '2023-02-28T03:00')
})
