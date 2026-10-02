import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

// Exercise the actual TypeScript selectors without adding a runtime/test library.
function sourceModule(path, dependencies = {}) {
  let source = ts.transpileModule(readFileSync(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  for (const [name, url] of Object.entries(dependencies)) source = source.replaceAll(`'${name}'`, `'${url}'`)
  return `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`
}
const selectorsUrl = sourceModule('../src/services/dashboardSelectors.ts')
const { buildMonitoringView, DEFAULT_FILTERS, mean } = await import(selectorsUrl)
const { buildAdminDashboardView } = await import(sourceModule('../src/services/adminDashboardModel.ts', { './dashboardSelectors': selectorsUrl }))

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
  assert.deepEqual(view.chartPoints, [{ label: '01/2026', value: 20 }])
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
