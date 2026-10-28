/** UI dates are day/month/year; transport and chronological keys remain ISO UTC. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return ''
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value
}

export function formatDateTime(value: string | null | undefined, seconds = false, timezone = false): string {
  if (!value) return ''
  let utc = value
  if (/[+-]\d{2}:\d{2}$/.test(value) && !value.endsWith('+00:00')) {
    const date = new Date(value)
    if (Number.isFinite(date.getTime())) utc = date.toISOString()
  }
  const time = /[T ](\d{2}:\d{2})(:\d{2}(?:\.\d+)?)?/.exec(utc)
  const label = /^\d{4}-\d{2}$/.test(utc) ? `${utc.slice(5, 7)}/${utc.slice(0, 4)}` : formatDate(utc).slice(0, 10)
  return `${label}${time ? ` ${time[1]}${seconds ? time[2] ?? ':00' : ''}` : ''}${timezone ? ' UTC' : ''}`
}

export function formatObservationTime(value: string, resolution: 'hourly' | '3h' | 'daily' | 'monthly') {
  return resolution === 'monthly' ? `Tháng ${value.slice(5, 7)}/${value.slice(0, 4)}`
    : resolution === 'daily' ? formatDate(value) : formatDateTime(value, false, true)
}

export function parseDisplayDate(value: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value)
  if (!match) return null
  const iso = `${match[3]}-${match[2]}-${match[1]}`
  const date = new Date(`${iso}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === iso ? iso : null
}

export function maskDisplayDate(value: string) {
  const digits = value.replace(/\D/g, '').slice(0, 8)
  return `${digits.slice(0, 2)}${digits.length > 2 ? `/${digits.slice(2, 4)}` : ''}${digits.length > 4 ? `/${digits.slice(4)}` : ''}`
}

export function isIsoDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  if (year < 1 || month < 1 || month > 12) return false
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  return day >= 1 && day <= days
}

export function parseVietnameseDate(value: string) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value)
  if (!match) return null
  const iso = `${match[3]}-${match[2]}-${match[1]}`
  return isIsoDate(iso) ? iso : null
}

export function shiftDateYear(value: string, offset: number) {
  if (!value) return ''
  const year = Number(value.slice(0, 4)) + offset
  const month = Number(value.slice(5, 7))
  const day = Math.min(Number(value.slice(8, 10)), new Date(Date.UTC(year, month, 0)).getUTCDate())
  return `${String(year).padStart(4, '0')}-${value.slice(5, 7)}-${String(day).padStart(2, '0')}${value.slice(10)}`
}
