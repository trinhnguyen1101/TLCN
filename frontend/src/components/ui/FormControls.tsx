import { Children, isValidElement, useId, useRef, useState, type InputHTMLAttributes, type LabelHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { formatDate, parseVietnameseDate } from '../../utils/dates'
import { DashboardIcon } from './DashboardIcon'

const controlClasses = 'h-10 w-full min-w-0 rounded-[7px] border border-border-strong bg-surface px-2.5 text-[.8rem] text-ink transition-[border-color,background-color,box-shadow] duration-150 ease-[ease] hover:border-muted focus:border-accent focus:ring-3 focus:ring-accent/15 focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-45 motion-reduce:transition-none'

export function Field({ className = '', inline = false, ...props }: LabelHTMLAttributes<HTMLLabelElement> & { inline?: boolean }) {
  return <label className={`grid min-w-0 text-[.76rem] font-medium text-secondary ${inline ? 'grid-cols-[auto_minmax(0,1fr)] items-center gap-4' : 'gap-2'} ${className}`} {...props} />
}

export function Select({ className = '', children, value, title, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  const selectedOption = Children.toArray(children).find((child) =>
    isValidElement<{ value?: string | number; children?: ReactNode }>(child) && String(child.props.value) === String(value))
  const selectedLabel = isValidElement<{ children?: ReactNode }>(selectedOption) ? selectedOption.props.children : '\u00a0'
  return (
    <span className="relative flex min-w-0">
      <select className={`${controlClasses} absolute inset-0 h-full! cursor-pointer appearance-none pr-[26px] text-transparent! [&_option]:text-ink ${className}`} value={value} title={title ?? (typeof selectedLabel === 'string' ? selectedLabel : undefined)} {...props}>{children}</select>
      <span aria-hidden="true" className={`pointer-events-none relative flex min-h-10 min-w-0 flex-1 items-center px-2.5 py-2 pr-8 text-[.8rem] leading-snug text-ink wrap-anywhere ${props.disabled ? 'opacity-45' : ''}`}><span>{selectedLabel}</span></span>
      <span className={`pointer-events-none absolute inset-y-0 right-2 flex items-center text-muted ${props.disabled ? 'opacity-45' : ''}`}><DashboardIcon name="chevronDown" size="small" /></span>
    </span>
  )
}

export function DateInput({ className = '', value, min, max, onValueChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'value' | 'min' | 'max' | 'onChange'> & {
  value: string; min?: string; max?: string; onValueChange: (value: string) => void
}) {
  const id = useId()
  const pickerRef = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState({ value, text: formatDate(value), touched: false })
  const text = draft.value === value ? draft.text : formatDate(value)
  const parsed = parseVietnameseDate(text)
  const error = !text ? '' : !parsed ? 'Nhập ngày hợp lệ theo dd/mm/yyyy.'
    : min && parsed < min ? `Ngày phải từ ${formatDate(min)} trở đi.`
    : max && parsed > max ? `Ngày phải trước hoặc bằng ${formatDate(max)}.` : ''
  const showError = Boolean(error && (text.length >= 10 || (draft.value === value && draft.touched)))
  return <span className="relative block min-w-0">
    <input type="text" lang="vi" placeholder="dd/mm/yyyy" maxLength={10} className={`${controlClasses} min-h-10 pr-9 ${className}`} {...props}
      value={text} aria-invalid={showError || props['aria-invalid']} aria-describedby={[props['aria-describedby'], showError ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined}
      onBlur={() => setDraft({ value, text, touched: true })}
      onChange={(event) => {
        const next = event.target.value
        const iso = parseVietnameseDate(next)
        const valid = iso !== null && (!min || iso >= min) && (!max || iso <= max)
        const committed = next === '' ? '' : valid ? iso! : value
        setDraft({ value: committed, text: next, touched: false })
        if (next === '' || valid) onValueChange(committed)
      }} />
    <input ref={pickerRef} type="date" lang="vi" className="sr-only" aria-hidden="true" tabIndex={-1} value={value} min={min} max={max} disabled={props.disabled}
      onChange={(event) => {
        const next = event.target.value
        if (!next || ((!min || next >= min) && (!max || next <= max))) {
          setDraft({ value: next, text: formatDate(next), touched: false })
          onValueChange(next)
        }
      }} />
    <button type="button" aria-label={`Chọn ${String(props['aria-label'] ?? 'ngày').toLowerCase()} trên lịch`} disabled={props.disabled}
      className="absolute top-0 right-0 flex size-10 cursor-pointer items-center justify-center rounded-md text-muted hover:text-accent focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed"
      onClick={() => {
        const picker = pickerRef.current
        if (picker?.showPicker) picker.showPicker()
        else picker?.focus()
      }}>
      <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18" /></svg>
    </button>
    {showError && <span id={`${id}-error`} role="alert" className="mt-1 block text-[.7rem] text-danger">{error}</span>}
  </span>
}
