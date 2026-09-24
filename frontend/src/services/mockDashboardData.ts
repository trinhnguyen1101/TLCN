import type {
  AirQualityStatus,
  EmissionRecord,
  ProvinceCode,
  ProvinceSnapshot,
  DashboardTrendRecord,
} from '../types/dashboard'

/**
 * Mock data for the dashboard prototype only. Values are deterministic and
 * intentionally illustrative; they are not scientific observations.
 */
const provinceSeed: Array<{
  code: ProvinceCode
  name: string
  aqi: number
  pm25: number
  pm10: number
}> = [
  { code: '01', name: 'Hà Nội', aqi: 145, pm25: 48, pm10: 71 },
  { code: '24', name: 'Bắc Ninh', aqi: 132, pm25: 43, pm10: 67 },
  { code: '22', name: 'Quảng Ninh', aqi: 93, pm25: 29, pm10: 51 },
  { code: '48', name: 'Đà Nẵng', aqi: 62, pm25: 17, pm10: 34 },
  { code: '79', name: 'TP. Hồ Chí Minh', aqi: 108, pm25: 34, pm10: 58 },
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
  aqi: province.aqi,
  status: getStatus(province.aqi),
  pm25: province.pm25,
  pm10: province.pm10,
}))

const emissionSeed: Array<[string, number]> = [
  ['Manufacturing', 760],
  ['Power', 615],
  ['Transport', 490],
  ['Residential', 285],
]

export const emissionRecords: EmissionRecord[] = provinceSeed.flatMap((province, provinceIndex) =>
  emissionSeed.map(([sector, baseEmission], sectorIndex) => ({
    provinceCode: province.code,
    provinceName: province.name,
    year: 2026,
    month: 6,
    sector,
    emissionTonnes: baseEmission - provinceIndex * 54 + (sectorIndex === 0 && province.code === '01' ? 120 : 0),
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
