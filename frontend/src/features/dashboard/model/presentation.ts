/** Translate display labels while preserving source identifiers used by filters. */
import { sectorLabel as localSectorLabel } from '../../../utils/labels'
const SECTORS: Record<string, string> = {
  manufacturing: 'Sản xuất công nghiệp', industry: 'Công nghiệp', industrial: 'Công nghiệp',
  power: 'Sản xuất điện', electricity: 'Sản xuất điện', energy: 'Năng lượng',
  transport: 'Giao thông', transportation: 'Giao thông', 'road transport': 'Giao thông đường bộ',
  residential: 'Dân sinh', buildings: 'Công trình xây dựng', commercial: 'Thương mại',
  agriculture: 'Nông nghiệp', forestry: 'Lâm nghiệp', 'land use': 'Sử dụng đất',
  waste: 'Chất thải', construction: 'Xây dựng', aviation: 'Hàng không', shipping: 'Hàng hải',
  other: 'Khác', others: 'Khác', all: 'Tất cả các ngành',
}

export function sectorLabel(value: string) {
  const key = value.trim().toLowerCase().replace(/[_-]/g, ' ').replace(/\s+/g, ' ')
  const local = localSectorLabel(value)
  return local !== value ? local : SECTORS[key] ?? value
}

export function sourceLabel(value?: string) {
  if (value === 'CAMS EAC4 hourly') return 'CAMS EAC4 · 1 giờ'
  if (value === 'cams') return 'CAMS EAC4 · mô hình'
  if (value === 'hourly_fixture') return 'Fixture 1 giờ · kiểm thử'
  if (value === 'CAMS EAC4 sample') return 'Dữ liệu mẫu CAMS EAC4'
  return value?.replace(/\bsample\b/gi, 'mẫu dữ liệu').replace(/\bmock demo\b/gi, 'Dữ liệu minh họa')
}

export function aggregationLabel(value: string) {
  return ({ '3_hourly': 'Quan sát mỗi 3 giờ', hourly: 'Dữ liệu mỗi giờ', hourly_mean: 'Trung bình giờ', daily_mean: 'Trung bình ngày', monthly_mean: 'Trung bình tháng' } as Record<string, string>)[value] ?? value
}

export function queryErrorMessage(detail: unknown) {
  if (typeof detail === 'string') {
    if (detail.includes('start must be before')) return 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.'
    if (detail.includes('3h queries support') || detail.includes('hourly queries support')) return 'Chế độ giờ hỗ trợ tối đa 31 ngày. Hãy rút ngắn khoảng thời gian hoặc chọn chế độ ngày.'
    if (detail.includes('daily queries support')) return 'Chế độ ngày hỗ trợ tối đa 366 ngày. Hãy rút ngắn khoảng thời gian hoặc chọn chế độ tháng.'
  }
  return 'Khoảng thời gian không hợp lệ. Vui lòng kiểm tra ngày, giờ và chế độ xem dữ liệu.'
}
