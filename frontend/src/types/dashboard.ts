export type AirQualityStatus = 'Tốt' | 'Trung bình' | 'Kém' | 'Xấu'

export type Pollutant = 'pm25' | 'pm10' | 'o3' | 'no2' | 'so2' | 'co'

export type ProvinceCode = '01' | '22' | '24' | '48' | '79'

export interface ProvinceSnapshot {
  provinceCode: ProvinceCode
  provinceName: string
  aqi: number
  status: AirQualityStatus
  pm25: number
  pm10: number
}

export interface EmissionRecord {
  provinceCode: ProvinceCode
  provinceName: string
  year: number
  month: number
  sector: string
  emissionTonnes: number
}

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
