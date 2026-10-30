import assert from 'node:assert/strict'
import test from 'node:test'
import {sourceModule} from './source-module.mjs'
const load = (path: string) => import(sourceModule(new URL(path, import.meta.url)))
const {DEFAULT_RESOLUTION, RESOLUTION_OPTIONS} = await load('../src/features/dashboard/model/resolution.ts')
const {vietnamInput, utcInput, formatDateTime} = await load('../src/utils/dates.ts')
const {presetPeriod, shiftPeriod} = await load('../src/features/dashboard/model/filterPeriods.ts')
const filters = {resolution:'hourly', provinceCode:'all', pollutant:'pm25', year:'all', month:'all', startDate:'2025-01-01T17:00', endDate:'2025-01-01T17:00', sector:'all'}
const metadata = {observationStart:'2025-01-01T00:00:00Z', observationEnd:'2025-01-31T23:00:00Z'}
test('Parquet defaults to hourly and offers daily and monthly', () => {
 assert.equal(DEFAULT_RESOLUTION,'hourly')
 assert.deepEqual(RESOLUTION_OPTIONS.map((x: {value: string})=>x.value),['hourly','daily','monthly'])
})
test('Vietnam midnight round trips through UTC on the previous day', () => {
 assert.equal(vietnamInput('2025-01-01T17:00:00Z'),'2025-01-02T00:00')
 assert.equal(utcInput('2025-01-02T00:00'),'2025-01-01T17:00')
 assert.equal(formatDateTime('2025-01-01T17:00:00Z',false,true),'02/01/2025 00:00 UTC+7')
})
test('hour navigation crosses midnight by one observation', () => {
 assert.equal(shiftPeriod(filters,1,metadata).endDate,'2025-01-01T18:00')
 assert.equal(shiftPeriod({...filters,startDate:'2025-01-01T23:00',endDate:'2025-01-01T23:00'},1,metadata).endDate,'2025-01-02T00:00')
})
test('hour presets contain precisely 24, 48 and 168 inclusive slots', () => {
 for (const [preset, slots] of [['24h',24],['48h',48],['7d',168]] as const) {
  const next = presetPeriod(filters,preset,metadata)
  assert.equal((Date.parse(`${next.endDate}Z`)-Date.parse(`${next.startDate}Z`))/3600000+1,slots)
 }
})
const {dataQuality} = await load('../src/features/dashboard/model/dataQuality.ts')
test('coverage counts completely absent hours and NULLs without zero filling', () => {
 const source = {provinceSnapshots:[{provinceCode:'01'}],dashboardTrendRecords:[{provinceCode:'01',date:'2025-01-01T00:00:00Z',pm25:0},{provinceCode:'01',date:'2025-01-01T02:00:00Z',pm25:null}],metadata:{cadenceHours:1}}
 const quality = dataQuality(source,{...filters,startDate:'2025-01-01T00:00',endDate:'2025-01-01T02:00'})
 assert.equal(quality.expected,3)
 assert.equal(quality.valid,1)
 assert.equal(quality.missing,2)
 assert.equal(quality.coverage,1/3)
})
test('daily coverage uses underlying hourly counts even for unavailable daily means', () => {
 const source = {provinceSnapshots:[{provinceCode:'01'}],dashboardTrendRecords:[{provinceCode:'01',date:'2025-01-01',pm25:null,metricSampleCounts:{pm25:17}}],metadata:{cadenceHours:1}}
 const quality = dataQuality(source,{...filters,resolution:'daily',startDate:'2025-01-01',endDate:'2025-01-01'})
 assert.equal(quality.expected,24)
 assert.equal(quality.valid,17)
 assert.equal(quality.missing,7)
})
const {metricOptions,basicPollutants,metricCategory}=await load('../src/features/dashboard/model/dashboardSelectors.ts')
const {formatDecimal}=await load('../src/utils/formatters.ts')
test('primary selector keeps seven pollutants separate from column and weather quantities', () => {
 const keys=['pm25','pm10','pm1','no2','so2','co','o3','coColumn','aod550','t2m']
 const source={provinceSnapshots:[],dashboardTrendRecords:[],metadata:{metrics:Object.fromEntries(keys.map(key=>[key,{unit:key==='co'?'mg/m³':'µg/m³',qualityStatus:'validated'}]))}}
 assert.deepEqual(metricOptions(source,true).map(x=>x.value),['pm25','pm10','pm1','no2','so2','co','o3'])
 assert.deepEqual(basicPollutants(source),['pm25','pm10','pm1','no2','so2','co','o3'])
 assert.equal(metricCategory('co'),'pollutants')
 assert.equal(metricCategory('coColumn'),'columns')
 assert.equal(metricCategory('t2m'),'weather')
 assert.equal(formatDecimal(.01825,'mg/m³'),'0,018 mg/m³')
 const missing={...source,metadata:{metrics:{co:{qualityStatus:'unavailable'},coColumn:{qualityStatus:'validated'}}}}
 assert.deepEqual(metricOptions(missing,true),[])
 assert.deepEqual(basicPollutants(missing),[])
})
