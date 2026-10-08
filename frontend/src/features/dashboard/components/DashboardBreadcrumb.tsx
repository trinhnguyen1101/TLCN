import type { BreadcrumbItem } from '../types'
import { DashboardIcon } from '../../../components/ui/DashboardIcon'

interface DashboardBreadcrumbProps {
  items: BreadcrumbItem[]
}

export function DashboardBreadcrumb({ items }: DashboardBreadcrumbProps) {
  return (
    <nav className="my-3" aria-label="Vị trí phân tích">
      <ol className="flex list-none flex-wrap items-center gap-[9px] p-0">
        {items.map((item, index) => (
          <li key={item.id} className="inline-flex min-w-0 max-w-full items-center gap-[9px] text-[.78rem] text-muted wrap-anywhere">
            {index > 0 && <DashboardIcon name="chevronRight" size="tiny" />}
            {item.onSelect ? <button className="min-w-0 cursor-pointer rounded-[3px] border-0 bg-transparent py-[3px] text-left text-muted hover:text-accent focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent" type="button" onClick={item.onSelect}>{item.label}</button> : <span className="min-w-0 aria-[current=location]:font-medium aria-[current=location]:text-ink" aria-current={index === items.length - 1 ? 'location' : undefined}>{item.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
