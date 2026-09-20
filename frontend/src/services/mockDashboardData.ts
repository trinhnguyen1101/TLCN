import type {
  AirQualityReading,
  AirQualityStatus,
  EmissionRecord,
  MonthlyTrend,
  PeriodComparison,
  Pollutant,
  PriorityArea,
  ProvinceCode,
  ProvinceSnapshot,
  DashboardTrendRecord,
} from '../types/dashboard'

/**
 * Mock data for the dashboard prototype only. Values are deterministic and
 * intentionally illustrative; they are not scientific observations.
 */
const DEMO_DATE = '2026-09-12'

const provinceSeed: Array<{
  code: ProvinceCode
  name: string
  latitude: number
  longitude: number
  aqi: number
  pm25: number
  pm10: number
  temperature: number
  humidity: number
  windSpeed: number
  primaryPollutant: Pollutant
  change: number
}> = [
  { code: '01', name: 'Hà Nội', latitude: 21.0285, longitude: 105.8542, aqi: 145, pm25: 48, pm10: 71, temperature: 30, humidity: 76, windSpeed: 1.8, primaryPollutant: 'pm25', change: 12 },
  { code: '24', name: 'Bắc Ninh', latitude: 21.1861, longitude: 106.0763, aqi: 132, pm25: 43, pm10: 67, temperature: 29, humidity: 74, windSpeed: 2.1, primaryPollutant: 'pm25', change: 9 },
  { code: '22', name: 'Quảng Ninh', latitude: 21.0064, longitude: 107.2925, aqi: 93, pm25: 29, pm10: 51, temperature: 28, humidity: 81, windSpeed: 3.6, primaryPollutant: 'pm25', change: -4 },
  { code: '48', name: 'Đà Nẵng', latitude: 16.0544, longitude: 108.2022, aqi: 62, pm25: 17, pm10: 34, temperature: 31, humidity: 70, windSpeed: 4.2, primaryPollutant: 'pm10', change: -7 },
  { code: '79', name: 'TP. Hồ Chí Minh', latitude: 10.8231, longitude: 106.6297, aqi: 108, pm25: 34, pm10: 58, temperature: 32, humidity: 73, windSpeed: 2.7, primaryPollutant: 'pm25', change: 5 },
]

const getStatus = (aqi: number): AirQualityStatus => {
  if (aqi <= 50) return 'Tốt'
  if (aqi <= 100) return 'Trung bình'
  if (aqi <= 150) return 'Kém'
  return 'Xấu'
}

export const provinceSnapshots: ProvinceSnapshot[] = provinceSeed.map((province) => ({
  provinceCode: province.code,
  provinceName: province.name,
  latitude: province.latitude,
  longitude: province.longitude,
  aqi: province.aqi,
  status: getStatus(province.aqi),
  pm25: province.pm25,
  pm10: province.pm10,
  temperature: province.temperature,
  humidity: province.humidity,
  windSpeed: province.windSpeed,
  primaryPollutant: province.primaryPollutant,
  changeFromYesterday: province.change,
  updatedAt: `${DEMO_DATE}T09:00:00+07:00`,
}))

// 24 hourly readings for the User dashboard. Highest values occur at 18:00–21:00.
export const hanoiHourlyReadings: AirQualityReading[] = Array.from({ length: 24 }, (_, hour) => {
  const eveningPeak = hour >= 18 && hour <= 21 ? 17 : 0
  const morningPeak = hour >= 7 && hour <= 9 ? 8 : 0
  const aqi = 103 + eveningPeak + morningPeak + (hour % 4) * 3
  const pm25 = Math.round(aqi * 0.33)

  return {
    provinceCode: '01',
    timestamp: `${DEMO_DATE}T${String(hour).padStart(2, '0')}:00:00+07:00`,
    aqi,
    pm25,
    pm10: pm25 + 22,
    o3: 38 + (hour % 6) * 3,
    no2: 24 + (hour % 5) * 2,
    so2: 8 + (hour % 3),
    co: 7 + (hour % 4),
    temperature: 26 + Math.min(hour, 14) * 0.42,
    humidity: 84 - Math.min(hour, 14),
    windSpeed: eveningPeak > 0 ? 1.3 : 2.1 + (hour % 3) * 0.3,
  }
})

// 30 daily readings support the 7-day/30-day trend, comparison and calendar views.
export const hanoiDailyReadings: AirQualityReading[] = Array.from({ length: 30 }, (_, index) => {
  const day = index + 1
  const spike = [8, 15, 23, 29].includes(day) ? 16 : 0
  const aqi = 96 + ((day * 7) % 25) + spike
  const pm25 = Math.round(aqi * 0.32)

  return {
    provinceCode: '01',
    timestamp: `2026-08-${String(day).padStart(2, '0')}T12:00:00+07:00`,
    aqi,
    pm25,
    pm10: pm25 + 21,
    o3: 40 + (day % 8) * 2,
    no2: 22 + (day % 6) * 2,
    so2: 7 + (day % 4),
    co: 6 + (day % 5),
    temperature: 28 + (day % 5) * 0.6,
    humidity: 78 - (day % 7),
    windSpeed: 1.5 + (day % 5) * 0.45,
  }
})

export const userPeriodComparisons: PeriodComparison[] = [
  { metric: 'aqi', currentLabel: 'Hôm nay', previousLabel: 'Hôm qua', currentValue: 145, previousValue: 129, changePercent: 12.4 },
  { metric: 'pm25', currentLabel: 'Tháng 9/2026', previousLabel: 'Tháng 8/2026', currentValue: 35.2, previousValue: 31.4, changePercent: 12.1 },
  { metric: 'pm25', currentLabel: 'Tháng 9/2026', previousLabel: 'Tháng 9/2025', currentValue: 35.2, previousValue: 32.5, changePercent: 8.3 },
]

const monthlyPm25 = [24, 25, 27, 25, 22, 20, 19, 21, 26, 30, 33, 31]
export const nationalMonthlyTrend: MonthlyTrend[] = [2024, 2025, 2026].flatMap((year, yearIndex) =>
  monthlyPm25.map((basePm25, monthIndex) => {
    const pm25Average = basePm25 + yearIndex * 2 + (year === 2026 && monthIndex === 2 ? 4 : 0)
    return {
      provinceCode: 'VNM',
      month: `${year}-${String(monthIndex + 1).padStart(2, '0')}`,
      pm25Average,
      pm10Average: pm25Average + 19,
      aqiAverage: Math.round(pm25Average * 3.2),
      exceedanceDays: Math.max(2, Math.round((pm25Average - 15) * 1.35)),
    }
  }),
)

export const adminProvinceTrend: MonthlyTrend[] = [
  { provinceCode: '01', month: '2024-01', pm25Average: 24, pm10Average: 43, aqiAverage: 77, exceedanceDays: 16 },
  { provinceCode: '01', month: '2025-01', pm25Average: 28, pm10Average: 48, aqiAverage: 90, exceedanceDays: 24 },
  { provinceCode: '01', month: '2026-01', pm25Average: 34, pm10Average: 56, aqiAverage: 109, exceedanceDays: 33 },
  { provinceCode: '24', month: '2026-01', pm25Average: 31, pm10Average: 53, aqiAverage: 99, exceedanceDays: 29 },
  { provinceCode: '48', month: '2026-01', pm25Average: 18, pm10Average: 36, aqiAverage: 58, exceedanceDays: 12 },
  { provinceCode: '79', month: '2026-01', pm25Average: 27, pm10Average: 46, aqiAverage: 86, exceedanceDays: 21 },
]

const emissionSeed: Array<[string, string, number]> = [
  ['Manufacturing', 'Cement', 760],
  ['Power', 'Coal-fired power', 615],
  ['Transport', 'Road transport', 490],
  ['Residential', 'Fuel combustion', 285],
]

export const emissionRecords: EmissionRecord[] = provinceSeed.flatMap((province, provinceIndex) =>
  emissionSeed.map(([sector, subsector, baseEmission], sectorIndex) => ({
    provinceCode: province.code,
    provinceName: province.name,
    year: 2026,
    month: 6,
    pollutant: 'pm2_5',
    sector,
    subsector,
    sourceType: sectorIndex === 3 ? 'gadm-aggregation' : 'point-source',
    emissionTonnes: baseEmission - provinceIndex * 54 + (sectorIndex === 0 && province.code === '01' ? 120 : 0),
    sourceCount: 4 + ((provinceIndex + sectorIndex) % 6),
  })),
)

export const priorityAreas: PriorityArea[] = [
  { provinceCode: '01', provinceName: 'Hà Nội', pm25Average: 35, yearOverYearPercent: 18, exceedanceDays: 42, priorityLevel: 'Cần chú ý', priorityScore: 92 },
  { provinceCode: '24', provinceName: 'Bắc Ninh', pm25Average: 32, yearOverYearPercent: 14, exceedanceDays: 38, priorityLevel: 'Cần chú ý', priorityScore: 84 },
  { provinceCode: '79', provinceName: 'TP. Hồ Chí Minh', pm25Average: 27, yearOverYearPercent: 8, exceedanceDays: 28, priorityLevel: 'Theo dõi', priorityScore: 63 },
  { provinceCode: '22', provinceName: 'Quảng Ninh', pm25Average: 24, yearOverYearPercent: 2, exceedanceDays: 20, priorityLevel: 'Theo dõi', priorityScore: 48 },
  { provinceCode: '48', provinceName: 'Đà Nẵng', pm25Average: 18, yearOverYearPercent: -5, exceedanceDays: 12, priorityLevel: 'Cải thiện', priorityScore: 22 },
]

/**
 * Monthly, province-level demo series used by the shared filter and comparison
 * components. The formula is stable so exports and comparisons are repeatable.
 */
export const dashboardTrendRecords: DashboardTrendRecord[] = provinceSeed.flatMap(
  (province, provinceIndex) =>
    [2025, 2026].flatMap((year) =>
      Array.from({ length: 12 }, (_, monthIndex) => {
        const seasonal = Math.round(Math.cos((monthIndex / 12) * Math.PI * 2) * 7)
        const yearIncrease = year === 2026 ? 4 : 0
        const pm25 = Math.max(8, province.pm25 - 13 + seasonal + yearIncrease - provinceIndex)
        return {
          provinceCode: province.code,
          date: `${year}-${String(monthIndex + 1).padStart(2, '0')}-15`,
          aqi: Math.round(pm25 * 3.05),
          pm25,
          pm10: pm25 + 20,
          o3: 35 + ((monthIndex + provinceIndex) % 7) * 3,
          no2: 20 + ((monthIndex * 2 + provinceIndex) % 9),
          so2: 7 + ((monthIndex + provinceIndex) % 5),
          co: 5 + ((monthIndex + provinceIndex) % 4),
        }
      }),
    ),
)

export const emissionSectors = [...new Set(emissionRecords.map((record) => record.sector))]

export const mockDashboardData = {
  demoDate: DEMO_DATE,
  provinceSnapshots,
  hanoiHourlyReadings,
  hanoiDailyReadings,
  userPeriodComparisons,
  nationalMonthlyTrend,
  adminProvinceTrend,
  emissionRecords,
  priorityAreas,
  dashboardTrendRecords,
  emissionSectors,
}
