import { useCallback, useId, useMemo, useRef, useState } from 'react'
import { FilterPopover } from './FilterPopover'
import { Button } from './Button'
import { DashboardIcon } from './DashboardIcon'

interface Props {
  label: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
  disabled?: boolean
}

const normalizeSearch = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLocaleLowerCase('vi').trim()

export function SearchSelect({ label, value, options, onChange, disabled }: Props) {
  const id = useId()
  const anchor = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [active, setActive] = useState(0)
  const close = useCallback(() => setOpen(false), [])
  const matches = useMemo(() => {
    const term = normalizeSearch(search)
    const rank = (option: Props['options'][number]) => normalizeSearch(option.label) === term || normalizeSearch(option.value) === term ? 0
      : normalizeSearch(option.label).startsWith(term) ? 1 : 2
    return options.filter((option) => normalizeSearch(`${option.label} ${option.value}`).includes(term))
      .sort((a, b) => rank(a) - rank(b))
  }, [options, search])
  const select = (next: string) => { onChange(next); close() }
  return <div className="min-w-0">
    <button ref={anchor} type="button" disabled={disabled} className="filter-select" title={options.find((option) => option.value === value)?.label} aria-label={label} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => { setSearch(''); setActive(0); setOpen(!open) }}>
      <span className="min-w-0 truncate"><span className="hidden text-muted sm:inline">{label}: </span>{options.find((option) => option.value === value)?.label ?? 'Chưa có dữ liệu'}</span>
      <DashboardIcon name={open ? 'chevronUp' : 'chevronDown'} size="small" className="text-muted" />
    </button>
    {open && <FilterPopover id={id} label={`Chọn ${label.toLocaleLowerCase('vi')}`} anchor={anchor} onClose={close}>
      <div className="flex items-center justify-between gap-2 p-3 pb-2"><span className="text-sm font-semibold text-heading">{label}</span><Button onClick={close} aria-label="Đóng lựa chọn">✕</Button></div>
      <div className="px-3 pb-2"><input data-autofocus type="search" className="filter-search" placeholder={`Tìm ${label.toLocaleLowerCase('vi')}…`} aria-label={`Tìm ${label.toLocaleLowerCase('vi')}`}
        role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls={`${id}-list`} aria-activedescendant={matches[active] ? `${id}-option-${active}` : undefined}
        value={search} onChange={(event) => { setSearch(event.target.value); setActive(0) }}
        onKeyDown={(event) => {
          if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
            event.preventDefault()
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? matches.length - 1 : Math.max(0, Math.min(matches.length - 1, active + (event.key === 'ArrowDown' ? 1 : -1)))
            setActive(next)
            document.getElementById(`${id}-option-${next}`)?.scrollIntoView({ block: 'nearest' })
          } else if (event.key === 'Enter' && matches[active]) { event.preventDefault(); select(matches[active].value) }
        }} /></div>
      <div id={`${id}-list`} role="listbox" aria-label={label} className="filter-option-list">
        {matches.map((option, index) => <button type="button" tabIndex={-1} id={`${id}-option-${index}`} role="option" aria-selected={option.value === value} key={option.value}
          className={`filter-option ${active === index ? 'filter-option-active' : ''}`} onPointerMove={() => setActive(index)} onClick={() => select(option.value)}>
          <span>{option.label}</span><span aria-hidden="true">{option.value === value ? '✓' : ''}</span>
        </button>)}
        {!matches.length && <p role="status" className="p-4 text-sm text-muted">Không có kết quả phù hợp.</p>}
      </div>
      <p className="border-t border-border px-3 py-2 text-xs text-muted">{matches.length} lựa chọn · ↑ ↓ để chọn · ↵ để áp dụng</p>
    </FilterPopover>}
  </div>
}
