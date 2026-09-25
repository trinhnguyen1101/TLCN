import type { InputHTMLAttributes, LabelHTMLAttributes, SelectHTMLAttributes } from 'react'

const controlClasses = 'h-10 w-full min-w-0 rounded-[7px] border border-border-strong bg-surface px-2.5 text-[.8rem] text-ink transition-[border-color,background-color,box-shadow] duration-150 ease-[ease] hover:border-muted focus:border-accent focus:shadow-[0_0_0_3px_rgb(94_234_212/12%)] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-45 motion-reduce:transition-none'

export function Field({ className = '', inline = false, ...props }: LabelHTMLAttributes<HTMLLabelElement> & { inline?: boolean }) {
  return <label className={`grid min-w-0 text-[.76rem] font-medium text-secondary ${inline ? 'grid-cols-[auto_minmax(0,1fr)] items-center gap-4' : 'gap-2'} ${className}`} {...props} />
}

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="relative block min-w-0">
      <select className={`${controlClasses} cursor-pointer appearance-none pr-[26px] ${className}`} {...props} />
      <svg className="pointer-events-none absolute top-1/2 right-[7px] size-4 -translate-y-1/2 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
        <path d="m7 10 5 5 5-5" />
      </svg>
    </span>
  )
}

export function DateInput({ className = '', ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  return <input type="date" className={`${controlClasses} min-h-10 ${className}`} {...props} />
}
