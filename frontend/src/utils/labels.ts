const SECTOR_LABELS: Record<string, string> = {
  Manufacturing: 'Sản xuất công nghiệp', Power: 'Sản xuất điện',
  Transport: 'Giao thông vận tải', Residential: 'Sinh hoạt dân cư',
}
export const sectorLabel = (value: string) => SECTOR_LABELS[value] ?? value
export const sourceLabel = (value: string) => value === 'CAMS EAC4 sample' ? 'Dữ liệu mẫu CAMS EAC4' : value
export const aggregationLabel = (value: string) => ({
  monthly_mean: 'Trung bình tháng', daily_mean: 'Trung bình ngày', hourly_mean: 'Trung bình giờ',
} as Record<string, string>)[value] ?? value
