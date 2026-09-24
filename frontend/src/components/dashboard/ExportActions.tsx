import { DashboardIcon } from './DashboardIcon'
import { Button } from '../ui/Button'

type CsvValue = string | number | null

interface ExportActionsProps {
  fileName: string
  chartId: string
  csvRows: Array<Record<string, CsvValue>>
}

const escapeCsvCell = (value: CsvValue) => `"${String(value ?? '').replaceAll('"', '""')}"`

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

export function ExportActions({ fileName, chartId, csvRows }: ExportActionsProps) {
  const exportCsv = () => {
    if (csvRows.length === 0) return
    const headers = Object.keys(csvRows[0])
    const csv = [headers.map(escapeCsvCell).join(','), ...csvRows.map((row) => headers.map((header) => escapeCsvCell(row[header])).join(','))].join('\n')
    downloadBlob(new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }), `${fileName}.csv`)
  }

  const exportChart = () => {
    const chart = document.getElementById(chartId)
    if (!(chart instanceof SVGElement)) return
    const clone = chart.cloneNode(true) as SVGElement
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
    downloadBlob(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' }), `${fileName}.svg`)
  }

  return (
    <div className="inline-flex flex-wrap gap-[7px]" aria-label="Tùy chọn xuất dữ liệu">
      <Button variant="export" onClick={exportChart} disabled={csvRows.length === 0} aria-label="Xuất biểu đồ SVG"><DashboardIcon name="download" size="tiny" />Xuất SVG</Button>
      <Button variant="export" onClick={exportCsv} disabled={csvRows.length === 0}><DashboardIcon name="download" size="tiny" />Xuất CSV</Button>
    </div>
  )
}
