/** Translate display labels while preserving source identifiers used by filters. */
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
  return SECTORS[key] ?? value
}

export function sourceLabel(value?: string) {
  if (value === 'CAMS EAC4 sample') return 'Dữ liệu mẫu CAMS EAC4'
  return value?.replace(/\bsample\b/gi, 'mẫu dữ liệu').replace(/\bmock demo\b/gi, 'Dữ liệu minh họa')
}

export function sourceNote(value?: string) {
  return value?.replace(/\bpipeline\b/gi, 'quy trình')
    .replace(/Các chỉ số \*_column là tổng cột/gi, 'Các chỉ số khí tổng cột được tính theo khối lượng trên diện tích')
    .replace(/\*_column/g, 'khí tổng cột')
    .replace('Không suy AQI hay ngày vượt ngưỡng từ dữ liệu này.', 'Dữ liệu này không dùng để suy ra AQI hay số ngày vượt ngưỡng.')
}

export function aggregationLabel(value: string) {
  return ({ '3_hourly': 'Quan sát mỗi 3 giờ', daily_mean: 'Trung bình ngày', monthly_mean: 'Trung bình tháng' } as Record<string, string>)[value] ?? 'Theo nguồn dữ liệu'
}

export function queryErrorMessage(detail: unknown) {
  if (typeof detail === 'string') {
    if (detail.includes('start must be before')) return 'Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.'
    if (detail.includes('3h queries support')) return 'Chế độ 3 giờ hỗ trợ tối đa 31 ngày. Hãy rút ngắn khoảng thời gian hoặc chọn chế độ ngày.'
    if (detail.includes('daily queries support')) return 'Chế độ ngày hỗ trợ tối đa 366 ngày. Hãy rút ngắn khoảng thời gian hoặc chọn chế độ tháng.'
  }
  return 'Khoảng thời gian không hợp lệ. Vui lòng kiểm tra ngày, giờ và chế độ xem dữ liệu.'
}
