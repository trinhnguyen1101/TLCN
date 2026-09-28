import { Button } from './Button'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  label: string
  itemLabel?: string
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function Pagination({
  page,
  pageSize,
  total,
  label,
  itemLabel = 'tỉnh',
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  if (total === 0) return null
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  return (
    <nav
      aria-label={label}
      className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-4 text-xs text-muted"
    >
      <p role="status" aria-live="polite">
        {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} / {total} {itemLabel}
      </p>
      <label className="flex items-center gap-2">
        Dòng/trang
        <select
          aria-label={`${label}: số dòng mỗi trang`}
          className="rounded border border-border bg-surface px-2 py-2 text-ink"
          value={pageSize}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
        >
          {[5, 10, 20].map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          disabled={page === 1}
          onClick={() => onPageChange(page - 1)}
          aria-label={`${label}: trang trước`}
        >
          ← Trước
        </Button>
        <span>
          Trang {page}/{pageCount}
        </span>
        <Button
          disabled={page === pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label={`${label}: trang sau`}
        >
          Sau →
        </Button>
      </div>
    </nav>
  )
}
