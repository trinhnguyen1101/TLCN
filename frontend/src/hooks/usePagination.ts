import { useState } from 'react'

export function usePagination(total: number, scope: string) {
  const [pageSize, setPageSize] = useState(10)
  const [selection, setSelection] = useState({ scope, page: 1 })
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const page = selection.scope === scope ? Math.min(selection.page, pageCount) : 1
  const offset = (page - 1) * pageSize
  return {
    page,
    pageSize,
    offset,
    total,
    onPageChange: (next: number) => setSelection({ scope, page: Math.max(1, Math.min(next, pageCount)) }),
    onPageSizeChange: (next: number) => {
      setPageSize(next)
      setSelection({ scope, page: 1 })
    },
  }
}
