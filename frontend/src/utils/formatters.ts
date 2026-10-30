export const formatDecimal = (value: number | null, unit = '', showUnit = true) => value === null
  ? 'Chưa có dữ liệu'
  : `${value.toLocaleString('vi-VN', { minimumFractionDigits: unit === 'mg/m³' ? 3 : 1, maximumFractionDigits: unit === 'mg/m³' ? 3 : 1 })}${unit && showUnit ? ` ${unit}` : ''}`
