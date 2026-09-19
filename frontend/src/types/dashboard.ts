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

export interface AirQualityReading {
  provinceCode: ProvinceCode
  timestamp: string
  aqi: number
  pm25: number
  pm10: number
  o3: number
  no2: number
  so2: number
  co: number
  temperature: number
  humidity: number
  windSpeed: number
}

export interface PeriodComparison {
  metric: 'aqi' | 'pm25' | 'pm10'
  currentLabel: string
  previousLabel: string
  currentValue: number
  previousValue: number
  changePercent: number
}

export interface MonthlyTrend {
  provinceCode: ProvinceCode | 'VNM'
  month: string
  pm25Average: number
  pm10Average: number
  aqiAverage: number
  exceedanceDays: number
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

export interface PriorityArea {
  provinceCode: ProvinceCode
  provinceName: string
  pm25Average: number
  yearOverYearPercent: number
  exceedanceDays: number
  priorityLevel: 'Cần chú ý' | 'Theo dõi' | 'Cải thiện'
  priorityScore: number
}
