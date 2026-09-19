import { useState } from 'react'
import { VietnamProvinceMap } from './features/geography/VietnamProvinceMap'
import type { ProvinceSnapshot } from './types/dashboard'
import './App.css'

function App() {
  const [selectedProvince, setSelectedProvince] = useState<ProvinceSnapshot | null>(null)

  return (
    <main className="app-shell">
      <header className="app-header">
        <p>Air Quality Dashboard · Demo</p>
        <h1>Bản đồ chất lượng không khí</h1>
        <span>Chọn một tỉnh có màu để xem nhanh dữ liệu mock.</span>
      </header>

      <VietnamProvinceMap onProvinceSelect={setSelectedProvince} />

      {selectedProvince && (
        <aside className="selected-province" aria-live="polite">
          <div>
            <p>Tỉnh đang chọn</p>
            <h2>{selectedProvince.provinceName}</h2>
          </div>
          <dl>
            <div><dt>AQI</dt><dd>{selectedProvince.aqi} · {selectedProvince.status}</dd></div>
            <div><dt>PM2.5</dt><dd>{selectedProvince.pm25} µg/m³</dd></div>
            <div><dt>Xu hướng</dt><dd>{selectedProvince.changeFromYesterday > 0 ? '↑' : '↓'} {Math.abs(selectedProvince.changeFromYesterday)}% so với hôm qua</dd></div>
          </dl>
        </aside>
      )}
    </main>
  )
}

export default App
