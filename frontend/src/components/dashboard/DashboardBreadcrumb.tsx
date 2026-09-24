import type { BreadcrumbItem } from '../../types/dashboard'
import './dashboardComponents.css'

interface DashboardBreadcrumbProps {
  items: BreadcrumbItem[]
}

export function DashboardBreadcrumb({ items }: DashboardBreadcrumbProps) {
  return (
    <nav className="dashboard-breadcrumb" aria-label="Vị trí phân tích">
      <ol>
        {items.map((item, index) => (
          <li key={item.id}>
            {index > 0 && <span aria-hidden="true">›</span>}
            {item.onSelect ? <button type="button" onClick={item.onSelect}>{item.label}</button> : <span aria-current={index === items.length - 1 ? 'location' : undefined}>{item.label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  )
}
