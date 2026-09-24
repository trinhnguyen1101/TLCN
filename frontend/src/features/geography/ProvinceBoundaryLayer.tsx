import { useState } from 'react'
import { GeoJSON, Tooltip } from 'react-leaflet'
import type { Path, PolylineOptions } from 'leaflet'
import type { ProvinceSnapshot } from '../../types/dashboard'
import type { ProvinceFeatureCollection } from './provinceMapData'
import type { MapMetric } from './VietnamProvinceMap'

interface ProvinceBoundaryLayerProps {
  data: ProvinceFeatureCollection
  selectedProvinceCode: string
  metric: MapMetric
  layerVisible: boolean
  metricsByProvince: Map<string, ProvinceSnapshot>
  onProvinceSelect?: (province: ProvinceSnapshot) => void
}

const selectedProvinceStyle: PolylineOptions = {
  color: 'var(--accent)', weight: 3, opacity: 1, fill: false,
  lineCap: 'round', lineJoin: 'round', smoothFactor: 0,
}

function getProvinceStyle(metrics: ProvinceSnapshot | undefined, metric: MapMetric, layerVisible: boolean): PolylineOptions {
  if (!metrics || !layerVisible) {
    return { color: 'var(--map-province-border)', fillColor: 'var(--map-province-fill)', fillOpacity: layerVisible ? .65 : .18, weight: 1, smoothFactor: 0, className: 'province-boundary' }
  }
  const value = metrics[metric]
  const limits = metric === 'aqi' ? [50, 100, 150] : metric === 'pm25' ? [15, 25, 35] : [30, 50, 75]
  const fillColor = value <= limits[0] ? '#22c55e' : value <= limits[1] ? '#eab308' : value <= limits[2] ? '#f97316' : '#dc2626'
  return { color: 'var(--surface-subtle)', fillColor, fillOpacity: .82, weight: 1.2, smoothFactor: 0, className: 'province-boundary' }
}

// The parent keys this layer by the dashboard selection so filters reset local selection.
export function ProvinceBoundaryLayer({ data, selectedProvinceCode, metric, layerVisible, metricsByProvince, onProvinceSelect }: ProvinceBoundaryLayerProps) {
  const [highlightedCode, setHighlightedCode] = useState(selectedProvinceCode)
  const highlightedFeature = data.features.find((feature) => feature.id === highlightedCode)

  return (
    <>
      {data.features.map((feature) => {
        const metrics = metricsByProvince.get(feature.id)
        const selectProvince = () => {
          setHighlightedCode(feature.id)
          if (metrics) onProvinceSelect?.(metrics)
        }

        return (
          <GeoJSON
            key={feature.id}
            data={feature}
            style={getProvinceStyle(metrics, metric, layerVisible)}
            onEachFeature={(_, layer) => {
              layer.on('add', () => {
                const element = (layer as Path).getElement()
                element?.setAttribute('tabindex', '0')
                element?.setAttribute('role', 'button')
                element?.setAttribute('aria-label', feature.properties.fullName)
              })
            }}
            eventHandlers={{
              click: selectProvince,
              keydown: (event) => {
                if (event.originalEvent.key === 'Enter' || event.originalEvent.key === ' ') {
                  event.originalEvent.preventDefault()
                  event.originalEvent.stopPropagation()
                  selectProvince()
                }
              },
            }}
          >
            <Tooltip sticky>
              <strong>{feature.properties.name}</strong><br />
              {metrics ? <>
                AQI: {metrics.aqi} · {metrics.status}<br />
                PM2.5: {metrics.pm25} µg/m³<br />
                PM10: {metrics.pm10} µg/m³
              </> : 'Chưa có dữ liệu'}
            </Tooltip>
          </GeoJSON>
        )
      })}
      {highlightedFeature && (
        <GeoJSON
          key={highlightedFeature.id}
          data={highlightedFeature}
          pane="province-selection"
          interactive={false}
          style={selectedProvinceStyle}
        />
      )}
    </>
  )
}
