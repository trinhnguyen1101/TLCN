import type { ButtonHTMLAttributes, HTMLAttributes } from 'react'

const variants = {
  secondary: 'min-h-9 gap-1.5 rounded-[7px] border border-border bg-surface px-2.5 py-[7px] text-[.76rem] text-secondary enabled:hover:border-accent-border enabled:hover:bg-accent-soft enabled:hover:text-accent',
  segment: 'min-h-7.5 rounded-[5px] border-0 bg-transparent px-3 py-1.5 text-[.76rem] text-muted hover:text-accent aria-pressed:bg-surface aria-pressed:text-accent aria-pressed:shadow-control',
  export: 'min-h-8.5 gap-1.5 rounded-[7px] border border-border bg-surface px-[9px] py-[7px] text-[.73rem] whitespace-nowrap text-secondary enabled:hover:border-accent-border enabled:hover:bg-accent-soft enabled:hover:text-accent',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants
}

export function Button({ variant = 'secondary', className = '', type = 'button', ...props }: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex cursor-pointer items-center justify-center font-medium transition-[border-color,background-color,box-shadow] duration-150 ease-[ease] [-webkit-tap-highlight-color:transparent] focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-45 motion-reduce:transition-none ${variants[variant]} ${className}`}
      {...props}
    />
  )
}

export function SegmentedControl({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div role="group" className={`inline-flex shrink-0 gap-[3px] rounded-lg border border-border bg-surface-subtle p-[3px] ${className}`} {...props} />
}
