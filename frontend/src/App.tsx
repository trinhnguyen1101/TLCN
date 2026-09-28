import { lazy, Suspense } from 'react'

const AdminDashboard = lazy(() =>
  import('./pages/admin/AdminDashboard').then((module) => ({ default: module.AdminDashboard })),
)

/** Keep one dashboard until role-specific routes are introduced. */
export default function App() {
  return (
    <Suspense
      fallback={
        <p role="status" className="p-8 text-muted">
          Đang tải dashboard…
        </p>
      }
    >
      <AdminDashboard />
    </Suspense>
  )
}
