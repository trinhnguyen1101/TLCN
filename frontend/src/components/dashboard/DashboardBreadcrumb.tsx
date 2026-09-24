import type { BreadcrumbItem } from '../../types/dashboard'

interface DashboardBreadcrumbProps {
  items: BreadcrumbItem[]
}

export function DashboardBreadcrumb({ items }: DashboardBreadcrumbProps) {
  return (
    <nav className="my-[22px]" aria-label="Vị trí phân tích">
      <ol className="flex list-none flex-wrap items-center gap-[9px] p-0">
        {items.map((item, index) => (
          <li key={item.id} className="inline-flex items-center gap-[9px] text-[.78rem] text-muted">
            {index > 0 && <span aria-hidden="true">›</span>}
            {item.onSelect ? <button className="cursor-pointer rounded-[3px] border-0 bg-transparent py-[3px] text-muted hover:text-accent focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" type="button" onClick={item.onSelect}>{item.label}</button> : <span className="aria-[current=location]:font-medium aria-[current=location]:text-ink" aria-current={index === items.length - 1 ? 'location' : undefined}>{item.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
