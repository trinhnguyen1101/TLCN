import type {
  AirQualityStatus,
  EmissionRecord,
  Pollutant,
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
