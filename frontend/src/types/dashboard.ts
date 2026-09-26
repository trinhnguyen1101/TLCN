export type AirQualityStatus = 'Tốt' | 'Trung bình' | 'Kém' | 'Xấu'

export type Pollutant = 'pm25' | 'pm10' | 'o3' | 'no2' | 'so2' | 'co' | 'pm1' | 'aod550' | 'o3Column' | 'no2Column' | 'so2Column' | 'coColumn' | 't2m' | 'd2m' | 'sp' | 'mslp' | 'u10' | 'v10'

export type ProvinceCode = string

export interface ProvinceSnapshot {
  provinceCode: ProvinceCode
  provinceName: string
  aqi: number | null
  status: AirQualityStatus | null
  pm25: number | null
  pm10: number | null
  pm1?: number | null
}

export interface EmissionRecord {
  provinceCode: ProvinceCode
  provinceName: string
  year: number
  month: number
  sector: string
  emissionTonnes: number
  sourceCount: number
}

export interface PriorityArea {
  provinceCode: ProvinceCode
  provinceName: string
  pm25Average: number
  yearOverYearPercent: number
  exceedanceDays: number
  totalEmissions: number | null
  mainEmissionSector: string | null
  trend: 'up' | 'slight-up' | 'steady' | 'down'
}

export interface AnnualProvinceSummary {
  provinceCode: ProvinceCode
  provinceName: string
  year: number
  pm25Average: number
  aqiAverage: number
  yearOverYearPercent: number
  exceedanceDays: number
}

export type DashboardProvince = ProvinceCode | 'all'

export interface DashboardFiltersValue {
  provinceCode: ProvinceCode | 'all'
  pollutant: Pollutant
  year: number | 'all'
  month: number | 'all'
  startDate: string
  endDate: string
  sector: string
}

export interface DashboardTrendRecord {
  provinceCode: ProvinceCode
  date: string
  pm25: number | null
  pm10: number | null
  o3: number | null
  no2: number | null
  so2: number | null
  co: number | null
  pm1?: number | null
  aod550?: number | null
  o3Column?: number | null
  no2Column?: number | null
  so2Column?: number | null
  coColumn?: number | null
  t2m?: number | null
  d2m?: number | null
  sp?: number | null
  mslp?: number | null
  u10?: number | null
  v10?: number | null
}

export interface ConcentrationScale {
  breakpoints: number[]
  method: 'absolute_concentration'
  sampleCount: number
  referenceStart: string
  referenceEnd: string
}

export interface MetricMetadata {
  unit: string
  quantity: string
  mapScale?: ConcentrationScale | null
}

export interface DashboardMetadata {
  source: string
  generation: string
  start: string
  end: string
  snapshotDate: string | null
  temporalAggregation: string
  timezone: string
  minimumSpatialCoverage: number
  minimumMonthlyCoverage: number
  metrics: Partial<Record<Pollutant, MetricMetadata>>
  note: string
}

export interface ChartPoint {
  label: string
  value: number
}

export interface BreadcrumbItem {
  id: string
  label: string
  onSelect?: () => void
}

export interface DashboardData {
  provinceSnapshots: ProvinceSnapshot[]
  emissionRecords: EmissionRecord[]
  emissionSectors: string[]
  dashboardTrendRecords: DashboardTrendRecord[]
  metadata?: DashboardMetadata | null
}
