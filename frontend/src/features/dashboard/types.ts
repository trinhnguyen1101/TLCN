export type AirQualityStatus = 'Tốt' | 'Trung bình' | 'Kém' | 'Xấu' | 'Rất xấu' | 'Nguy hại'

export type Pollutant = 'aqi' | 'pm25' | 'pm10' | 'o3' | 'no2' | 'so2' | 'co' | 'pm1' | 'aod550' | 'o3Column' | 'no2Column' | 'so2Column' | 'coColumn' | 't2m' | 'd2m' | 'sp' | 'mslp' | 'u10' | 'v10'

export type ProvinceCode = string

export interface ProvinceSnapshot extends Partial<Record<Pollutant, number | null>> {
  metricQuality?: Partial<Record<Pollutant,{qualityStatus?:string|null;missingReason?:string|null;observationTime?:string|null;coverage?:number|null}>>
  aqiStatus?: string | null
  provinceCode: ProvinceCode
  provinceName: string
  aqi: number | null
  status: AirQualityStatus | null
  pm25: number | null
  pm10: number | null
  pm1?: number | null
  source?: string | null
  seriesId?: string | null
  observationTime?: string | null
  sourceResolutionMinutes?: number | null
  temporalSupport?: string | null
  applicabilityProfile?: string | null
  qualityStatus?: string | null
  aqiMissingReason?: string | null
  coverage?: number | null
  aqiMethodVersion?: string | null
  publishedReleaseId?: string | null
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
  pm25Average: number | null
  yearOverYearPercent: number | null
  exceedanceDays: number | null
  totalEmissions: number | null
  mainEmissionSector: string | null
  trend: 'up' | 'slight-up' | 'steady' | 'down' | null
}

export interface AnnualProvinceSummary {
  provinceCode: ProvinceCode
  provinceName: string
  year: number
  pm25Average: number
  aqiAverage: number | null
  yearOverYearPercent: number | null
  exceedanceDays: number | null
}

export type DashboardProvince = ProvinceCode | 'all'

export interface DashboardFiltersValue {
  resolution: 'hourly' | '3h' | 'daily' | 'monthly'
  provinceCode: ProvinceCode | 'all'
  pollutant: Pollutant
  year: number | 'all'
  month: number | 'all'
  startDate: string
  endDate: string
  sector: string
}

export interface DashboardTrendRecord {
  metricSampleCounts?: Partial<Record<Pollutant, number>> | null
  aqi?: number | null
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
  version?: string | null
  statistic?: string | null
  referenceKind?: string | null
  note?: string | null
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
  publishedTimelineId?: string | null
  compatibilityId?: string | null
  publishedReleaseIds?: string[]
  missingScopes?: Array<{start:string;end:string;reason:string}>
  publishedReleaseId?: string | null
  source: string
  generation: string
  start: string
  end: string
  snapshotDate: string | null
  temporalAggregation: string
  timezone: string
  minimumSpatialCoverage: number | null
  minimumMonthlyCoverage: number | null
  metrics: Partial<Record<Pollutant, MetricMetadata>>
  note: string
  queryStart?: string | null
  queryEnd?: string | null
  availableYears?: number[]
  observationStart?: string | null
  observationEnd?: string | null
}

export interface ChartPoint {
  breakBefore?: boolean
  label: string
  value: number
  timestamp?: string
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
  comparisonTrendRecords?: DashboardTrendRecord[]
}

export interface AdminTrendRecord extends DashboardTrendRecord {
  aqi?: number | null
}

export interface AdminDashboardData {
  provinceSnapshots: ProvinceSnapshot[]
  emissionRecords: EmissionRecord[]
  emissionSectors: string[]
  dashboardTrendRecords: AdminTrendRecord[]
  priorityAreas: PriorityArea[]
  annualProvinceSummaries: AnnualProvinceSummary[]
  metadata?: DashboardMetadata | null
  comparisonTrendRecords?: AdminTrendRecord[]
}

export interface AnalyticsStatistics {
  mean: number | null
  median: number | null
  minimum: number | null
  maximum: number | null
  validCount: number
  expectedCount: number
}

export interface ProvinceRank extends AnalyticsStatistics {
  provinceCode: ProvinceCode
  provinceName: string
  rank: number
}

export interface MetricRanking {
  metric: Pollutant
  unit: string
  rows: ProvinceRank[]
}

export interface DashboardAnalytics {
  summary: AnalyticsStatistics
  provinceCount: number
  months: string[]
  rankings: MetricRanking[]
  timeline: Array<{ date: string; values: Record<string, number | null> }>
  provinceSnapshots: ProvinceSnapshot[]
  generation: string | null
}
