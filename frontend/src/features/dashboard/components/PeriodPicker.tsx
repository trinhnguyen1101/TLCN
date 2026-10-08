import { useCallback, useId, useRef, useState } from 'react'
import type { DashboardFiltersValue, DashboardMetadata } from '../types'
import { FilterPopover } from '../../../components/ui/FilterPopover'
import { Button, SegmentedControl } from '../../../components/ui/Button'
import { DateInput, Select } from '../../../components/ui/FormControls'
import { DashboardIcon } from '../../../components/ui/DashboardIcon'
import { calendarPeriod, periodYears } from '../model/temporal'
import { presetPeriod, shiftPeriod, shortPeriod, sourceBounds, validatePeriod, type PeriodPreset } from '../model/filterPeriods'
import { formatDate, formatDateTime } from '../../../utils/dates'

interface Props {
  value: DashboardFiltersValue
  years: number[]
  metadata?: DashboardMetadata | null
  onChange: (value: DashboardFiltersValue) => void
}
const HOURS = Array.from({ length: 8 }, (_, i) => `${String(i * 3).padStart(2, '0')}:00`)
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
const isoDay = (year: number, month: number, day: number) => `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`

function CalendarMonth({ year, month, start, end, min, max, onPick }: {
  year: number; month: number; start: string; end: string; min: string; max: string; onPick: (date: string) => void
}) {
  const first = (new Date(Date.UTC(year, month, 1)).getUTCDay() + 6) % 7
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const [focusDay, setFocusDay] = useState(() => start.slice(0, 7) === isoDay(year, month, 1).slice(0, 7)
    ? Number(start.slice(8, 10)) : min.slice(0, 7) === isoDay(year, month, 1).slice(0, 7) ? Number(min.slice(8, 10)) : 1)
  return <div className="period-calendar">
    <div className="grid grid-cols-7 text-center text-[.7rem] text-muted" aria-hidden="true">{['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'].map((day) => <span key={day} className="pb-2">{day}</span>)}</div>
    <div className="grid grid-cols-7 gap-y-1" role="group" aria-label={`Lịch tháng ${month + 1} năm ${year}`}>
      {Array.from({ length: first }, (_, i) => <span key={`empty-${i}`} />)}
      {Array.from({ length: days }, (_, i) => {
        const date = isoDay(year, month, i + 1)
        const edge = date === start || date === end
        return <button type="button" key={date} tabIndex={focusDay === i + 1 ? 0 : -1} onFocus={() => setFocusDay(i + 1)} aria-label={`Ngày ${i + 1} tháng ${month + 1} năm ${year}`} aria-pressed={edge}
          disabled={Boolean(min && date < min || max && date > max)}
          className={`calendar-day ${edge ? 'calendar-edge' : start && end && date > start && date < end ? 'calendar-range' : ''}`}
          onClick={() => onPick(date)} onKeyDown={(event) => {
            const offset = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[event.key]
            if (offset === undefined) return
            event.preventDefault()
            const buttons = [...event.currentTarget.parentElement!.querySelectorAll<HTMLButtonElement>('button')]
            buttons[i + offset]?.focus()
          }}>{i + 1}</button>
      })}
    </div>
  </div>
}

function PeriodEditor({ value, years, metadata, onApply, onClose }: Props & { onApply: (next: DashboardFiltersValue) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(value)
  const [single, setSingle] = useState(Boolean(value.startDate && value.startDate === value.endDate && value.resolution === '3h'))
  const [pickingEnd, setPickingEnd] = useState(false)
  const [editingTime, setEditingTime] = useState<'startDate' | 'endDate' | null>(null)
  const [quickOpen, setQuickOpen] = useState(false)
  const dateId = useId()
  const timeButtons = useRef<Partial<Record<'startDate' | 'endDate', HTMLButtonElement | null>>>({})
  const bounds = sourceBounds(metadata, draft.resolution)
  const initial = value.endDate || bounds.end
  const [visibleMonth, setVisibleMonth] = useState(initial.slice(0, 7) || `${years[0]}-01`)
  const [year, month] = visibleMonth.split('-').map(Number)
  const availableYears = periodYears(metadata, years, draft.resolution)
  const error = validatePeriod(draft, metadata)
  const previous = shiftPeriod(draft, -1, metadata)
  const next = shiftPeriod(draft, 1, metadata)
  const presets: Array<{ id: PeriodPreset; label: string }> = [
    { id: '7d', label: '7 ngày gần nhất' }, { id: '30d', label: '30 ngày gần nhất' },
    { id: 'month', label: 'Tháng gần nhất' }, ...(draft.resolution !== '3h' ? [{ id: 'year' as const, label: 'Năm gần nhất' }] : []),
    ...(draft.resolution === 'monthly' ? [{ id: 'history' as const, label: 'Toàn bộ thời gian' }] : []),
  ]
  const navigate = (offset: number) => {
    const date = new Date(Date.UTC(year, month - 1 + offset, 1))
    setVisibleMonth(date.toISOString().slice(0, 7))
  }
  const pick = (date: string) => {
    if (single) {
      const time = draft.startDate.split('T')[1] || '00:00'
      setDraft({ ...draft, year: 'all', month: 'all', startDate: `${date}T${time}`, endDate: `${date}T${time}` })
      return
    }
    if (!pickingEnd || date < draft.startDate.slice(0, 10)) {
      setDraft({ ...draft, year: 'all', month: 'all', startDate: `${date}${draft.resolution === '3h' ? 'T00:00' : ''}`, endDate: `${date}${draft.resolution === '3h' ? 'T21:00' : ''}` })
      setPickingEnd(true)
    } else {
      setDraft({ ...draft, endDate: `${date}${draft.resolution === '3h' ? 'T21:00' : ''}` })
      setPickingEnd(false)
    }
  }
  const updateDate = (key: 'startDate' | 'endDate', date: string) => {
    const time = draft[key].split('T')[1] || (key === 'startDate' ? '00:00' : '21:00')
    const next = date ? `${date}${draft.resolution === '3h' ? `T${time}` : ''}` : ''
    setDraft({ ...draft, year: 'all', month: 'all', ...(single ? { startDate: next, endDate: next } : { [key]: next }) })
  }
  const latest = () => {
    const next = presetPeriod(draft, 'latest', metadata)
    setDraft(next); setPickingEnd(false); setEditingTime(null)
    if (bounds.end) setVisibleMonth(bounds.end.slice(0, 7))
  }
  return <form className="period-editor" onSubmit={(event) => { event.preventDefault(); if (!error) onApply(draft) }}>
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3"><div><h2 className="text-sm font-semibold text-heading">Chọn thời gian</h2><p className="mt-1 text-xs text-muted">Giờ quốc tế (UTC) · {draft.resolution === '3h' ? 'Tối đa 31 ngày' : draft.resolution === 'daily' ? 'Tối đa 366 ngày' : 'Lịch sử theo tháng'}</p></div><Button onClick={onClose} aria-label="Đóng lịch">✕</Button></div>
    <div className="period-editor-body">
      <div className="period-mode-controls"><SegmentedControl aria-label="Xem dữ liệu theo">
        {([{ value: '3h', label: '3 giờ' }, { value: 'daily', label: 'Ngày' }, { value: 'monthly', label: 'Tháng' }] as const).map((option) => <Button key={option.value} variant="segment" aria-pressed={draft.resolution === option.value} onClick={() => {
          setDraft({ ...draft, resolution: option.value, year: 'all', month: 'all', startDate: '', endDate: '' }); setSingle(false); setEditingTime(null)
          const end = sourceBounds(metadata, option.value).end
          if (end) setVisibleMonth(end.slice(0, 7))
          setPickingEnd(false)
        }}>{option.label}</Button>)}
      </SegmentedControl>
      {draft.resolution === '3h' && <SegmentedControl aria-label="Cách chọn thời gian">
        <Button variant="segment" aria-label="Chọn khoảng thời gian" aria-pressed={!single} onClick={() => { setSingle(false); setPickingEnd(false); setEditingTime(null) }}>Khoảng ngày</Button>
        <Button variant="segment" aria-pressed={single} onClick={() => {
          setSingle(true); setPickingEnd(false); setEditingTime(null)
          const date = draft.endDate || bounds.end.slice(0, 16)
          setDraft({ ...draft, year: 'all', month: 'all', startDate: date, endDate: date })
        }}>Một thời điểm</Button>
      </SegmentedControl>}
      </div>
      {!single && <div className="period-presets">
        <div className="flex items-center justify-between gap-2"><button type="button" className="period-quick-toggle" aria-expanded={quickOpen} aria-controls={quickOpen ? `${dateId}-presets` : undefined} onClick={() => setQuickOpen(!quickOpen)}>Chọn nhanh khoảng thời gian <DashboardIcon name={quickOpen ? 'chevronUp' : 'chevronDown'} size="tiny" /></button><button type="button" className="cursor-pointer text-xs text-accent underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-accent" onClick={latest}>Đặt lại</button></div>
        {quickOpen && <div id={`${dateId}-presets`} className="mt-2"><div className="flex flex-wrap gap-1.5" aria-label="Chọn nhanh khoảng thời gian">{presets.map((preset) => <Button key={preset.id} className="min-h-8! text-xs!" onClick={() => {
        const next = presetPeriod(draft, preset.id, metadata)
        setDraft(next); setPickingEnd(false); setEditingTime(null); setQuickOpen(false)
        if (next.startDate) setVisibleMonth(next.startDate.slice(0, 7))
      }}>{preset.label}</Button>)}</div>
        {bounds.end && <p className="mt-2 text-[.7rem] leading-relaxed text-muted">Tính đến ngày có dữ liệu gần nhất: {formatDate(bounds.end)}.</p>}</div>}
      </div>}
      <div className="period-endpoints" data-single={single} role="group" aria-label={single ? 'Thời điểm quan sát' : 'Ngày bắt đầu và ngày kết thúc'}>
        {!single && <span className="period-endpoint-connector" aria-hidden="true"><DashboardIcon name="arrowRight" size="small" /></span>}
        {(single ? ['startDate'] as const : ['startDate', 'endDate'] as const).map((key) => <div key={key} className="period-endpoint" data-endpoint={key} data-active={single || (key === 'endDate') === pickingEnd} onFocusCapture={() => { if (!single) setPickingEnd(key === 'endDate') }}>
          <label htmlFor={`${dateId}-${key}`} className="period-endpoint-label">{!single && <span className="period-endpoint-number" aria-hidden="true">{key === 'startDate' ? '1' : '2'}</span>}{single ? 'Thời điểm quan sát' : key === 'startDate' ? 'Bắt đầu' : 'Kết thúc'}</label>
          <div className="period-date-control">
            <DateInput id={`${dateId}-${key}`} aria-label={single ? 'Ngày quan sát' : key === 'startDate' ? 'Từ ngày' : 'Đến ngày'} value={draft[key].split('T')[0]} onValueChange={(date) => updateDate(key, date)} aria-describedby={error ? 'period-error' : undefined} />
            {draft.resolution === '3h' && <button type="button" className="period-time-toggle" ref={(button) => { timeButtons.current[key] = button }} aria-label={`Chọn ${single ? 'giờ quan sát' : key === 'startDate' ? 'giờ bắt đầu' : 'giờ kết thúc'} UTC`} aria-expanded={editingTime === key} aria-controls={editingTime === key ? `${dateId}-${key}-hours` : undefined} disabled={!/^\d{4}-\d{2}-\d{2}/.test(draft[key])} onClick={() => setEditingTime(editingTime === key ? null : key)}><DashboardIcon name="clock" size="tiny" />{draft[key].split('T')[1] || (key === 'startDate' ? '00:00' : '21:00')}<DashboardIcon name={editingTime === key ? 'chevronUp' : 'chevronDown'} size="tiny" /></button>}
          </div>
          {draft.resolution === '3h' && editingTime === key && <div id={`${dateId}-${key}-hours`} className={`mt-2 grid ${single ? 'grid-cols-4 sm:grid-cols-8' : 'grid-cols-4'} gap-1`} role="group" aria-label={`${single ? 'Giờ quan sát' : key === 'startDate' ? 'Giờ bắt đầu' : 'Giờ kết thúc'} UTC`}>{HOURS.map((hour) => <button key={hour} type="button" className="period-hour" aria-pressed={draft[key].split('T')[1] === hour} disabled={!/^\d{4}-\d{2}-\d{2}/.test(draft[key])} onClick={() => {
            const instant = `${draft[key].split('T')[0]}T${hour}`
            setDraft({ ...draft, ...(single ? { startDate: instant, endDate: instant } : { [key]: instant }) })
            setEditingTime(null)
            timeButtons.current[key]?.focus({ preventScroll: true })
          }}>{hour}</button>)}</div>}
        </div>)}
      </div>
      <div className="period-calendar-section">
      {draft.resolution !== 'monthly' && <p className="period-calendar-guidance" aria-live="polite"><DashboardIcon name="calendar" size="tiny" />{single ? 'Chọn ngày quan sát trên lịch' : pickingEnd ? 'Đang chọn ngày kết thúc' : 'Đang chọn ngày bắt đầu'}</p>}
      <div className="flex items-center justify-between gap-2">
        <Button variant="icon" onClick={() => navigate(-1)} aria-label="Tháng trước" disabled={Boolean(bounds.start && visibleMonth <= bounds.start.slice(0, 7))}><DashboardIcon name="chevronLeft" /></Button>
        <div className="grid min-w-0 grid-cols-2 gap-2"><Select aria-label="Tháng trên lịch" value={month} onChange={(event) => setVisibleMonth(`${year}-${event.target.value.padStart(2, '0')}`)}>{MONTHS.map((m) => <option key={m} value={m}>Tháng {m}</option>)}</Select><Select aria-label="Năm trên lịch" value={year} onChange={(event) => setVisibleMonth(`${event.target.value}-${String(month).padStart(2, '0')}`)}>{availableYears.map((y) => <option key={y} value={y}>{y}</option>)}</Select></div>
        <Button variant="icon" onClick={() => navigate(1)} aria-label="Tháng sau" disabled={Boolean(bounds.end && visibleMonth >= bounds.end.slice(0, 7))}><DashboardIcon name="chevronRight" /></Button>
      </div>
      {draft.resolution === 'monthly' ? <div className="mt-3 grid grid-cols-3 gap-2" role="group" aria-label={`Chọn tháng năm ${year}`}>{MONTHS.map((m) => <Button key={m} aria-pressed={draft.startDate.slice(0, 7) === `${year}-${String(m).padStart(2, '0')}`} disabled={Boolean(bounds.start && `${year}-${String(m).padStart(2, '0')}` < bounds.start.slice(0, 7) || bounds.end && `${year}-${String(m).padStart(2, '0')}` > bounds.end.slice(0, 7))}
        onClick={() => setDraft(calendarPeriod(draft, availableYears, year, m))}>Tháng {m}</Button>)}</div>
        : <div className="mt-3"><CalendarMonth key={`${year}-${month}`} year={year} month={month - 1} start={draft.startDate.slice(0, 10)} end={draft.endDate.slice(0, 10)} min={bounds.start.slice(0, 10)} max={bounds.end.slice(0, 10)} onPick={pick} /></div>}
      <p className="mt-2 text-xs leading-relaxed text-muted">{single ? 'Chọn ngày trên lịch và bấm vào giờ để đổi giờ quan sát.' : draft.resolution === 'monthly' ? 'Chọn một tháng trên lịch hoặc nhập ngày bắt đầu và kết thúc.' : pickingEnd ? 'Chọn ngày kết thúc trên lịch. Bấm vào ô Bắt đầu để đổi ngày bắt đầu.' : 'Chọn ngày bắt đầu trên lịch, sau đó chọn ngày kết thúc.'}</p>
      {draft.resolution !== '3h' && <Button className="mt-3" onClick={() => setDraft(calendarPeriod(draft, availableYears, year, 'all'))}>Chọn cả năm {year}</Button>}
      </div>
      {error && <p id="period-error" role="alert" className="mt-3 rounded-lg bg-danger-soft p-2.5 text-xs leading-relaxed text-danger">{error}</p>}
      <div className="mt-3 flex gap-2 sm:hidden">{([{ value: previous, label: 'Khoảng trước', icon: 'chevronLeft' }, { value: next, label: 'Khoảng sau', icon: 'chevronRight' }] as const).map((period) => <Button key={period.label} disabled={!period.value} onClick={() => {
        if (!period.value) return
        setDraft(period.value); setVisibleMonth(period.value.startDate.slice(0, 7)); setPickingEnd(false)
      }}><DashboardIcon name={period.icon} size="small" />{period.label}</Button>)}</div>
      {bounds.start && bounds.end && <p className="mt-3 text-[.7rem] text-muted">Dữ liệu có từ {formatDate(bounds.start)} đến {formatDate(bounds.end)}.</p>}
    </div>
    <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border bg-surface px-4 py-3"><Button onClick={onClose}>Hủy</Button><Button type="submit" disabled={Boolean(error)} className="border-accent! bg-accent! px-5! text-surface! enabled:hover:bg-accent-hover!">Áp dụng</Button></div>
  </form>
}

export function PeriodPicker(props: Props) {
  const id = useId()
  const anchor = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])
  return <div className="min-w-0">
    <button type="button" ref={anchor} disabled={!props.value.endDate && !sourceBounds(props.metadata, props.value.resolution).end} className="filter-select" title={`${formatDateTime(props.value.startDate)} → ${formatDateTime(props.value.endDate)} UTC`} aria-label="Chọn khoảng thời gian" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen(!open)}>
      <DashboardIcon name="calendar" size="small" /><span className="min-w-0"><span className="hidden truncate sm:block">{shortPeriod(props.value)}</span><span className="grid text-left text-xs leading-tight sm:hidden">{props.value.startDate ? <><span>{formatDate(props.value.startDate)}</span>{props.value.resolution === '3h' && props.value.startDate === props.value.endDate && <span>{props.value.endDate.slice(11, 16)}</span>}{props.value.startDate.slice(0, 10) !== props.value.endDate.slice(0, 10) && <span>{formatDate(props.value.endDate)}</span>}</> : shortPeriod(props.value)}</span></span><span className="shrink-0 text-[.65rem] text-muted"><span className="sm:hidden">{props.value.resolution === '3h' ? '3 giờ' : props.value.resolution === 'daily' ? 'Ngày' : 'Tháng'} · </span>UTC</span>
    </button>
    {open && <FilterPopover id={id} label="Chọn khoảng thời gian" anchor={anchor} onClose={close} centered><PeriodEditor {...props} onClose={close} onApply={(next) => { props.onChange(next); close() }} /></FilterPopover>}
  </div>
}
