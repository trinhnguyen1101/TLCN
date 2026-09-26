import { AdminDashboard } from './pages/admin/AdminDashboard'
import UserDashboard from './pages/user/UserDashboard'

/** Application-level route selection; page implementations live under pages/. */
export default function App() {
  const path = window.location.pathname.replace(/\/$/, '') || '/user'

  if (path === '/admin') return <AdminDashboard />
  return <UserDashboard />
}
