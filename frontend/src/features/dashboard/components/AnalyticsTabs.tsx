import { useId, type ReactNode } from 'react'

export interface AnalyticsTab { id: string; label: string }
export function AnalyticsTabs({ tabs, value, onChange, children }: { tabs: AnalyticsTab[]; value: string; onChange: (value: string) => void; children: ReactNode }) {
  const id = useId()
  return <section className="mt-5 min-w-0" aria-label="Phân tích chuyên sâu">
    <div role="tablist" aria-label="Nhóm phân tích" className="mb-4 flex flex-wrap gap-1 border-b border-border pb-2">
      {tabs.map((tab, index) => <button key={tab.id} id={`${id}-${tab.id}`} role="tab" type="button" aria-selected={value === tab.id} aria-controls={`${id}-panel`} tabIndex={value === tab.id ? 0 : -1} onClick={() => onChange(tab.id)} onKeyDown={(event) => {
        const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index - 1 + tabs.length) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null
        if (next !== null) { event.preventDefault(); onChange(tabs[next].id); document.getElementById(`${id}-${tabs[next].id}`)?.focus() }
      }} className="rounded-md px-3 py-2 text-xs font-medium text-muted hover:text-accent focus-visible:outline-2 focus-visible:outline-accent aria-selected:bg-accent-soft aria-selected:text-accent">{tab.label}</button>)}
    </div>
    <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${value}`} tabIndex={0} className="min-w-0 focus-visible:outline-2 focus-visible:outline-accent">{children}</div>
  </section>
}
