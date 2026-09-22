import { AdminDashboard } from './pages/admin/AdminDashboard'
import './App.css'

function App() {
  if (window.location.pathname !== '/admin') {
    window.history.replaceState(null, '', `/admin${window.location.search}${window.location.hash}`)
  }

  return <AdminDashboard />
}

export default App
