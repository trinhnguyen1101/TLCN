import { Children, isValidElement, type InputHTMLAttributes, type LabelHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { formatDate, maskDisplayDate, parseDisplayDate } from '../../utils/dates'
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

export function DateInput({ className = '', value, onValueChange, ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> & { value: string; onValueChange: (value: string) => void }) {
  const display = formatDate(value)
  return <input {...props} type="text" inputMode="numeric" placeholder="dd/mm/yyyy" maxLength={10} autoComplete="off"
    value={display} aria-invalid={Boolean(display && !parseDisplayDate(display))} className={`${controlClasses} min-h-10 tabular-nums ${className}`}
    onChange={(event) => {
      const masked = maskDisplayDate(event.target.value)
      onValueChange(parseDisplayDate(masked) ?? masked)
    }} />
}
