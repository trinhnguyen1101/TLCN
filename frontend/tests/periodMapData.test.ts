import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildPeriodMapSnapshots } from '../src/features/geography/periodMapData.ts'
import type { DashboardData, DashboardFiltersValue } from '../src/types/dashboard.ts'

const filters: DashboardFiltersValue = { provinceCode: 'all', pollutant: 'pm25', year: 'all', month: 'all', startDate: '', endDate: '', sector: 'all' }
const data: DashboardData = {
  provinceSnapshots: ['a', 'b'].map(code => ({ provinceCode: code, provinceName: code, pm1: 999, pm25: 999, pm10: 999, aqi: 50, status: 'Tốt' })),
  dashboardTrendRecords: [
    { provinceCode: 'a', date: '2024-01-01', pm1: 5, pm25: 10, pm10: 20 },
    { provinceCode: 'a', date: '2025-01-01', pm1: 15, pm25: 30, pm10: 40 },
    { provinceCode: 'b', date: '2025-01-01', pm1: 0, pm25: 0, pm10: null },
  ].map(record => ({ o3: null, no2: null, so2: null, co: null, ...record })),
  emissionRecords: [], emissionSectors: [],
}

test('map reads monthly source values without an analytics response', () => {
  const result = buildPeriodMapSnapshots(data, filters)
  assert.equal(result[0].pm25, 20)
  assert.equal(result[0].aqi, null)
  assert.equal(result[1].pm25, 0)
  assert.equal(result[1].pm10, null)
  assert.equal(data.provinceSnapshots[0].pm25, 999)
})
test('map follows mid-month ranges and keeps national context on province selection', () => {
  const scopedFilters: DashboardFiltersValue = { ...filters, provinceCode: 'a', startDate: '2025-01-15', endDate: '2025-01-20' }
  const result = buildPeriodMapSnapshots(data, scopedFilters)
  assert.equal(result.length, 2)
  assert.equal(result[0].pm25, 30)
  assert.equal(result[1].pm25, 0)
})
test('empty map period never reuses latest snapshot values', () => {
  const result = buildPeriodMapSnapshots(data, { ...filters, year: 2030 })
  assert.ok(result.every(province => province.pm25 === null && province.pm10 === null))
})
test('duplicate monthly records receive equal month weight', () => {
  const duplicate = { ...data.dashboardTrendRecords[0], pm25: 20 }
  const result = buildPeriodMapSnapshots({ ...data, dashboardTrendRecords: [...data.dashboardTrendRecords, duplicate] }, filters)
  assert.equal(result[0].pm25, 22.5)
})

test('reversed dates do not display a valid-looking map', () => {
  const result = buildPeriodMapSnapshots(data, { ...filters, startDate: '2025-01-20', endDate: '2025-01-15' })
  assert.ok(result.every(province => province.pm25 === null))
})
