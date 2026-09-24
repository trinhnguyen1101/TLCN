export type AirQualityStatus = 'Tốt' | 'Trung bình' | 'Kém' | 'Xấu'

export type Pollutant = 'pm25' | 'pm10' | 'o3' | 'no2' | 'so2' | 'co'

export type ProvinceCode = '01' | '22' | '24' | '48' | '79'

export interface ProvinceSnapshot {
  provinceCode: ProvinceCode
  provinceName: string
  latitude: number
  longitude: number
  aqi: number
  status: AirQualityStatus
  pm25: number
  pm10: number
  temperature: number
  humidity: number
  windSpeed: number
  primaryPollutant: Pollutant
  changeFromYesterday: number
  updatedAt: string
}

export interface EmissionRecord {
  provinceCode: ProvinceCode
  provinceName: string
  year: number
  month: number
  pollutant: 'pm2_5' | 'so2' | 'co2'
  sector: string
  subsector: string
  sourceType: 'point-source' | 'gadm-aggregation'
  emissionTonnes: number
  sourceCount: number
}

export type DashboardProvince = ProvinceCode | 'all'

export interface DashboardFiltersValue {
  provinceCode: DashboardProvince
  pollutant: Pollutant
  year: number | 'all'
  month: number | 'all'
  startDate: string
  endDate: string
  sector: string | 'all'
}

export interface DashboardTrendRecord {
  provinceCode: ProvinceCode
  date: string
  aqi: number
  pm25: number
  pm10: number
  o3: number
  no2: number
  so2: number
  co: number
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
