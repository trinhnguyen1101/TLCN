import type { Pollutant } from '../types/dashboard'

export const METRIC_META: Record<Pollutant, { label: string; unit: string }> = {
  pm25: { label: 'PM2.5', unit: 'µg/m³' },
  pm10: { label: 'PM10', unit: 'µg/m³' },
  o3: { label: 'O₃', unit: 'µg/m³' },
  no2: { label: 'NO₂', unit: 'µg/m³' },
  so2: { label: 'SO₂', unit: 'µg/m³' },
  co: { label: 'CO', unit: 'mg/m³' },
  pm1: { label: 'PM1', unit: 'µg/m³' },
  aod550: { label: 'AOD 550 nm', unit: '1' },
  o3Column: { label: 'O₃ tổng cột', unit: 'mg/m²' },
  no2Column: { label: 'NO₂ tổng cột', unit: 'mg/m²' },
  so2Column: { label: 'SO₂ tổng cột', unit: 'mg/m²' },
  coColumn: { label: 'CO tổng cột', unit: 'mg/m²' },
  t2m: { label: 'Nhiệt độ 2 m', unit: '°C' },
  d2m: { label: 'Điểm sương 2 m', unit: '°C' },
  sp: { label: 'Áp suất bề mặt', unit: 'hPa' },
  mslp: { label: 'Áp suất mực biển', unit: 'hPa' },
  u10: { label: 'Gió 10 m hướng đông', unit: 'm/s' },
  v10: { label: 'Gió 10 m hướng bắc', unit: 'm/s' },
}
