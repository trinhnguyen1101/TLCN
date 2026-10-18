import { lazy, Suspense } from 'react'

const AdminDashboard = lazy(() =>
  import('./pages/admin/AdminDashboard').then((module) => ({ default: module.AdminDashboard })),
)
const UserDashboard = lazy(() => import('./pages/user/UserDashboard'))

function dashboardForPath(pathname: string) {
  const path = pathname.replace(/\/+$/, '') || '/'
  if (path === '/' || path === '/admin') return <AdminDashboard />
  if (path === '/user') return <UserDashboard />
  return (
    <main className="mx-auto grid min-h-screen max-w-xl place-content-center gap-4 px-6 text-center">
      <h1 className="text-2xl font-semibold text-heading">Không tìm thấy trang</h1>
      <p className="text-sm text-muted">Đường dẫn này không thuộc dashboard quản lý hoặc dashboard người dùng.</p>
      <nav className="flex justify-center gap-3" aria-label="Chọn dashboard">
        <a className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-surface" href="/admin">Trang quản lý</a>
        <a className="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-secondary" href="/user">Trang người dùng</a>
      </nav>
    </main>
  )
}

export default function App() {
  return (
    <Suspense
      fallback={
        <p role="status" className="p-8 text-muted">
          Đang tải dashboard…
        </p>
      }
    >
      {dashboardForPath(window.location.pathname)}
    </Suspense>
  )
}
