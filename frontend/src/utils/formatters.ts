export const formatDecimal = (value: number | null, unit = '') => value === null
  ? 'Chưa có dữ liệu'
  : `${value.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}${unit ? ` ${unit}` : ''}`
