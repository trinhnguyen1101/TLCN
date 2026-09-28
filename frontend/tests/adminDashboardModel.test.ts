import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildAdminDashboardView } from '../src/services/adminDashboardModel.ts'
import type { AdminDashboardData, DashboardFiltersValue } from '../src/types/dashboard.ts'

const filters: DashboardFiltersValue = {
  provinceCode: 'all',
  pollutant: 'pm25',
  year: 'all',
  month: 'all',
  startDate: '',
  endDate: '',
  sector: 'all',
}
const data: AdminDashboardData = {
  provinceSnapshots: ['a', 'b'].map((code) => ({
    provinceCode: code,
    provinceName: code,
    aqi: null,
    status: null,
    pm25: null,
    pm10: null,
  })),
  dashboardTrendRecords: [
    { provinceCode: 'a', date: '2024-01-01', pm25: 10 },
    { provinceCode: 'a', date: '2025-01-01', pm25: 30 },
    { provinceCode: 'b', date: '2025-01-01', pm25: 20 },
  ].map((row) => ({ pm10: null, o3: null, no2: null, so2: null, co: null, ...row })),
  emissionRecords: [2024, 2025].map((year) => ({
    provinceCode: 'a',
    provinceName: 'a',
    year,
    month: 1,
    sector: 'Transport',
    emissionTonnes: 10,
    sourceCount: 1,
  })),
  emissionSectors: ['Transport'],
  annualProvinceSummaries: [
    {
      provinceCode: 'a',
      provinceName: 'a',
      year: 2025,
      pm25Average: 30,
      aqiAverage: null,
      yearOverYearPercent: null,
      exceedanceDays: 24,
    },
  ],
  priorityAreas: [
    {
      provinceCode: 'a',
      provinceName: 'a',
      pm25Average: 999,
      yearOverYearPercent: 999,
      exceedanceDays: 24,
      totalEmissions: 999,
      mainEmissionSector: 'Old',
      trend: 'up',
    },
  ],
}

test('all years aggregates all selected records and emissions', () => {
  const view = buildAdminDashboardView(data, filters)
  assert.equal(view.currentPm25, 20)
  assert.equal(view.totalEmissions, 20)
})
test('province drilldown scopes the highest-province KPI to the selected province', () => {
  const view = buildAdminDashboardView(data, { ...filters, provinceCode: 'a', year: 2025 })
  assert.equal(view.currentPm25, 30)
  assert.deepEqual(view.provinceRanking, [{ id: 'a', label: 'a', value: 30 }])
  assert.equal(view.bestProvince?.id, 'a')
})
test('mid-month dates select monthly values and never prorate exceedance counts', () => {
  const view = buildAdminDashboardView(data, {
    ...filters,
    provinceCode: 'a',
    startDate: '2025-01-15',
    endDate: '2025-01-20',
  })
  assert.equal(view.currentPm25, 30)
  assert.equal(view.totalEmissions, 10)
  assert.equal(view.filteredEmissionRecords.length, 1)
  assert.equal(view.exceedanceDays, null)
  assert.equal(view.priorityAreaRows[0].exceedanceDays, null)
})
test('empty filtered scope never falls back to stale annual values', () => {
  const view = buildAdminDashboardView(data, { ...filters, month: 2 })
  assert.equal(view.currentPm25, null)
  assert.equal(view.priorityAreaRows[0].pm25Average, null)
  assert.equal(view.priorityAreaRows[0].totalEmissions, null)
  assert.equal(view.priorityAreaRows[0].yearOverYearPercent, null)
})


test('year-over-year compares only matching province-month pairs', () => {
  const view = buildAdminDashboardView(data, { ...filters, year: 2025 })
  // Province b has no 2024 baseline; it must not dilute province a's 10 → 30 change.
  assert.equal(view.yoy, 200)
})
