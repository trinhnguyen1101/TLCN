import type { ReactNode } from 'react'

const icons = {
  air: <><path d="M3 8h12a3 3 0 1 0-3-3" /><path d="M2 12h17a3 3 0 1 1-3 3" /><path d="M4 16h5a3 3 0 1 1-3 3" /></>,
  location: <><path d="M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
  chart: <><path d="M4 4v16h16" /><path d="m7 14 4-4 4 2 5-7" /></>,
  emission: <><path d="M3 21V10l6 3V8l6 4V3h5l1 18Z" /><path d="M7 17h1m4 0h1m4 0h1" /></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 11h18m-13 4h2m4 0h2" /></>,
  reset: <><path d="M3 10a9 9 0 1 1 2 8M3 4v6h6" /></>,
  filter: <><path d="M4 7h16M4 17h16" /><circle cx="9" cy="7" r="2" fill="currentColor" /><circle cx="15" cy="17" r="2" fill="currentColor" /></>,
  download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
  layers: <><path d="m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5" /></>,
} satisfies Record<string, ReactNode>

export function DashboardIcon({ name, className = '' }: { name: keyof typeof icons; className?: string }) {
  return (
    <svg className={`dashboard-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {icons[name]}
    </svg>
  )
}
