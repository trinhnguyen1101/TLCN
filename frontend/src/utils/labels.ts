const SECTOR_LABELS: Record<string, string> = {
  Manufacturing: 'Sản xuất công nghiệp', Power: 'Sản xuất điện',
  Transport: 'Giao thông vận tải', Residential: 'Sinh hoạt dân cư',
}
export const sectorLabel = (value: string) => SECTOR_LABELS[value] ?? value
export const sourceLabel = (value: string) => value === 'CAMS EAC4 hourly' ? 'CAMS EAC4 · 1 giờ' : value === 'cams' ? 'CAMS EAC4 · mô hình' : value === 'hourly_fixture' ? 'Fixture 1 giờ · kiểm thử' : value === 'CAMS EAC4 sample' ? 'Dữ liệu mẫu CAMS EAC4' : value
export const aggregationLabel = (value: string) => ({
  hourly_native_samples: 'Slot giờ · mẫu gốc của nguồn', daily_available_sample_mean: 'Trung bình mẫu thực trong ngày (giờ Việt Nam)', monthly_sample_weighted_mean: 'Trung bình mẫu thực trong tháng (giờ Việt Nam)', monthly_mean: 'Trung bình tháng', daily_mean: 'Trung bình ngày', hourly: 'Dữ liệu mỗi giờ', hourly_mean: 'Trung bình giờ',
} as Record<string, string>)[value] ?? value
